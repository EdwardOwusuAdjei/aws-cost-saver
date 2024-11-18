import boto3
import pandas as pd
from datetime import datetime, timezone
import os
from botocore.exceptions import ClientError
from botocore.config import Config
import logging
from typing import Dict, Any

my_config = Config(
    region_name='us-east-1',
    retries={'max_attempts': 10}
)

class AWSResourceAuditor:
    def __init__(self):
        self.ec2 = boto3.client('ec2')
        self.pricing = boto3.client('pricing', config=my_config)
        self.output_dir = f"aws_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(self.output_dir, exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f"{self.output_dir}/audit.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.pricing_data = self._get_pricing_data()

    def _get_pricing_data(self) -> Dict[str, float]:
        region_name = self.ec2.meta.region_name
        self.logger.info(f"Gathering pricing information for {region_name}...")
        prices = {}
        
        try:
            gp2_response = self.pricing.get_products(
                ServiceCode='AmazonEC2',
                Filters=[
                    {'Type': 'TERM_MATCH', 'Field': 'volumeApiName', 'Value': 'gp2'},
                    {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Storage'},
                    {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': region_name}
                ]
            )
            if gp2_response['PriceList']:
                prices['gp2'] = float(list(list(eval(gp2_response['PriceList'][0])['terms']['OnDemand'].values())[0]['priceDimensions'].values())[0]['pricePerUnit']['USD'])

            gp3_response = self.pricing.get_products(
                ServiceCode='AmazonEC2',
                Filters=[
                    {'Type': 'TERM_MATCH', 'Field': 'volumeApiName', 'Value': 'gp3'},
                    {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Storage'},
                    {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': region_name}
                ]
            )
            if gp3_response['PriceList']:
                prices['gp3'] = float(list(list(eval(gp3_response['PriceList'][0])['terms']['OnDemand'].values())[0]['priceDimensions'].values())[0]['pricePerUnit']['USD'])

            eip_response = self.pricing.get_products(
                ServiceCode='AmazonEC2',
                Filters=[
                    {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'IP Address'},
                    {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': region_name}
                ]
            )
            if eip_response['PriceList']:
                prices['eip'] = float(list(list(eval(eip_response['PriceList'][0])['terms']['OnDemand'].values())[0]['priceDimensions'].values())[0]['pricePerUnit']['USD'])

            region_prefix = region_name.split('-')[0].upper()
            snapshot_response = self.pricing.get_products(
                ServiceCode='AmazonEC2',
                Filters=[
                    {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Storage Snapshot'},
                    {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': region_name},
                    {'Type': 'TERM_MATCH', 'Field': 'usagetype', 'Value': f'{region_prefix}-EBS:SnapshotUsage'}
                ]
            )
            if snapshot_response['PriceList']:
                for price_item in snapshot_response['PriceList']:
                    price_data = eval(price_item)
                    if 'SnapshotUsage' in price_data['product']['attributes'].get('usagetype', ''):
                        prices['snapshot'] = float(
                            list(list(price_data['terms']['OnDemand'].values())[0]['priceDimensions'].values())[0]['pricePerUnit']['USD']
                        )
                        break
                
                if 'snapshot' not in prices:
                    self.logger.warning(f"Could not find regular snapshot pricing for region {region_name}, using default")
                    prices['snapshot'] = 0.05 

        except Exception as e:
            self.logger.error(f"Error fetching pricing data: {e}")
            prices = {'gp2': 0.10, 'gp3': 0.08, 'eip': 0.005, 'snapshot': 0.05}
            self.logger.info("Falling back to approximate pricing...")
            
        return prices

    def get_instance_name(self, instance: Dict[str, Any]) -> str:
        tags = instance.get('Tags', [])
        return next((tag['Value'] for tag in tags if tag['Key'] == 'Name'), 'No Name')

    def get_oldest_instances(self, limit: int = 200) -> pd.DataFrame:
        self.logger.info(f"Finding oldest {limit} EC2 instances...")
        instances = []
        
        try:
            paginator = self.ec2.get_paginator('describe_instances')
            for page in paginator.paginate():
                for reservation in page['Reservations']:
                    for instance in reservation['Instances']:
                        if instance['State']['Name'] != 'terminated':
                            instances.append({
                                'InstanceId': instance['InstanceId'],
                                'Name': self.get_instance_name(instance),
                                'LaunchTime': instance['LaunchTime'],
                                'InstanceType': instance['InstanceType'],
                                'State': instance['State']['Name'],
                                'Platform': instance.get('Platform', 'linux'),
                                'VpcId': instance.get('VpcId', 'None'),
                                'PrivateIp': instance.get('PrivateIpAddress', 'None'),
                                'PublicIp': instance.get('PublicIpAddress', 'None')
                            })
        except ClientError as e:
            self.logger.error(f"Error fetching EC2 instances: {e}")
            return pd.DataFrame()

        df = pd.DataFrame(instances)
        if not df.empty:
            df['LaunchTime'] = pd.to_datetime(df['LaunchTime'])
            df['Age_Days'] = (pd.Timestamp.now(tz=timezone.utc) - df['LaunchTime']).dt.total_seconds() / (24 * 3600)
            df['Age_Days'] = df['Age_Days'].round(2)
            df['LaunchTime'] = df['LaunchTime'].dt.strftime('%Y-%m-%d %H:%M:%S')
            
            df = df.sort_values('Age_Days', ascending=False).head(limit)
            return df
            
        return pd.DataFrame()

    def get_snapshots_with_duplicates(self) -> pd.DataFrame:
        self.logger.info("Finding duplicate snapshots...")
        snapshots = []
        
        try:
            paginator = self.ec2.get_paginator('describe_snapshots')
            for page in paginator.paginate(OwnerIds=['self']):
                for snapshot in page['Snapshots']:
                    snapshots.append({
                        'SnapshotId': snapshot['SnapshotId'],
                        'VolumeId': snapshot.get('VolumeId', 'N/A'),
                        'StartTime': snapshot['StartTime'],
                        'Size': snapshot['VolumeSize'],
                        'Description': snapshot.get('Description', 'No description')
                    })
        except ClientError as e:
            self.logger.error(f"Error fetching snapshots: {e}")
            return pd.DataFrame()

        df = pd.DataFrame(snapshots)
        if not df.empty:
            volume_counts = df['VolumeId'].value_counts()
            duplicate_volumes = volume_counts[volume_counts > 1].index
            duplicates = df[df['VolumeId'].isin(duplicate_volumes)].copy()
            
            if len(duplicates) > 0:
                duplicates['DuplicateCount'] = duplicates['VolumeId'].map(volume_counts)
                duplicates['StartTime'] = pd.to_datetime(duplicates['StartTime'])
                duplicates['IsNewest'] = duplicates.groupby('VolumeId')['StartTime'].transform('max') == duplicates['StartTime']
                snapshot_price = self.pricing_data.get('snapshot', 0.05)  # Price per GB-month
                duplicates['MonthlyCost'] = duplicates['Size'] * snapshot_price
                duplicates['PotentialMonthlySavings'] = duplicates.apply(
                    lambda x: x['MonthlyCost'] if not x['IsNewest'] else 0, 
                    axis=1
                )
                current_time = pd.Timestamp.now(tz=timezone.utc)
                duplicates['Age_Days'] = (current_time - duplicates['StartTime']).dt.total_seconds() / (24 * 3600)
                duplicates = duplicates.sort_values(
                    ['DuplicateCount', 'VolumeId', 'StartTime'],
                    ascending=[False, True, True]
                )
                duplicates['StartTime'] = duplicates['StartTime'].dt.strftime('%Y-%m-%d %H:%M:%S')
                duplicates['Age_Days'] = duplicates['Age_Days'].round(2)
                return duplicates
        
        return pd.DataFrame()

    def get_top_gp2_instances(self, limit: int = 50) -> pd.DataFrame:
        self.logger.info("Finding instances with largest GP2 storage...")
        volumes = []
        
        try:
            paginator = self.ec2.get_paginator('describe_volumes')
            for page in paginator.paginate(Filters=[{'Name': 'volume-type', 'Values': ['gp2']}]):
                for volume in page['Volumes']:
                    if volume['Attachments']:
                        volumes.append({
                            'InstanceId': volume['Attachments'][0]['InstanceId'],
                            'VolumeId': volume['VolumeId'],
                            'Size': volume['Size']  # Size in GB
                        })
        except ClientError as e:
            self.logger.error(f"Error fetching volumes: {e}")
            return pd.DataFrame()

        df = pd.DataFrame(volumes)
        if not df.empty:
            instance_storage = df.groupby('InstanceId').agg({
                'Size': 'sum',
                'VolumeId': 'count'
            }).reset_index()
            
            instance_storage.columns = ['InstanceId', 'TotalGP2Storage', 'VolumeCount']
            instance_storage = instance_storage.sort_values('TotalGP2Storage', ascending=False).head(limit)
            
            # monthly savings (price difference between GP2 and GP3 per GB-month)
            price_diff = self.pricing_data.get('gp2', 0.10) - self.pricing_data.get('gp3', 0.08)
            instance_storage['MonthlySavings'] = instance_storage['TotalGP2Storage'] * price_diff
            
            names = []
            for instance_id in instance_storage['InstanceId']:
                try:
                    response = self.ec2.describe_instances(InstanceIds=[instance_id])
                    instance = response['Reservations'][0]['Instances'][0]
                    names.append(self.get_instance_name(instance))
                except:
                    names.append('Unknown')
            
            instance_storage['Name'] = names
            return instance_storage
        return pd.DataFrame()

    def get_unused_elastic_ips(self) -> pd.DataFrame:
        self.logger.info("Finding unused Elastic IPs...")
        unused_ips = []
        
        try:
            addresses = self.ec2.describe_addresses()
            for addr in addresses['Addresses']:
                if 'AssociationId' not in addr:
                    unused_ips.append({
                        'PublicIp': addr['PublicIp'],
                        'AllocationId': addr.get('AllocationId', 'N/A'),
                        'Domain': addr['Domain']
                    })
        except ClientError as e:
            self.logger.error(f"Error fetching Elastic IPs: {e}")
            return pd.DataFrame()

        df = pd.DataFrame(unused_ips)
        if not df.empty:
            # Calculate monthly cost (hourly rate * 24 * 30)
            hourly_rate = self.pricing_data.get('eip', 0.005)
            df['MonthlyCost'] = hourly_rate * 24 * 30
        return df

    def save_to_files(self, df: pd.DataFrame, name: str):
        if not df.empty:
            csv_path = f"{self.output_dir}/{name}.csv"
            df.to_csv(csv_path, index=False)
            
            md_path = f"{self.output_dir}/{name}.md"
            with open(md_path, 'w') as f:
                f.write(f"# {name.replace('_', ' ').title()}\n\n")
                f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(df.to_markdown(index=False))

    def get_stopped_instances_cost(self, age_threshold_days: int = 0) -> pd.DataFrame:
        self.logger.info(f"Finding stopped instances and their costs...")
        instances = []
        
        try:
            paginator = self.ec2.get_paginator('describe_instances')
            for page in paginator.paginate(
                Filters=[{'Name': 'instance-state-name', 'Values': ['stopped']}]
            ):
                for reservation in page['Reservations']:
                    for instance in reservation['Instances']:
                        instance_data = {
                            'InstanceId': instance['InstanceId'],
                            'Name': self.get_instance_name(instance),
                            'LaunchTime': instance['LaunchTime'],
                            'InstanceType': instance['InstanceType'],
                            'Platform': instance.get('Platform', 'linux'),
                            'VpcId': instance.get('VpcId', 'None'),
                            'StopTime': instance.get('StateTransitionReason', 'Unknown'),
                            'TotalStorageGB': 0,
                            'StorageCost': 0.0
                        }
                        
                        launch_time = pd.to_datetime(instance['LaunchTime'])
                        instance_data['Age_Days'] = (pd.Timestamp.now(tz=timezone.utc) - launch_time).total_seconds() / (24 * 3600)
                        
                        try:
                            volumes_response = self.ec2.describe_volumes(
                                Filters=[{'Name': 'attachment.instance-id', 'Values': [instance['InstanceId']]}]
                            )
                            
                            for volume in volumes_response['Volumes']:
                                instance_data['TotalStorageGB'] += volume['Size']
                                volume_type = volume['VolumeType']
                                if volume_type == 'gp2':
                                    price = self.pricing_data.get('gp2', 0.10)
                                elif volume_type == 'gp3':
                                    price = self.pricing_data.get('gp3', 0.08)
                                else:
                                    price = 0.10  # Default price per GB-month
                                
                                instance_data['StorageCost'] += volume['Size'] * price
                                
                        except Exception as e:
                            self.logger.error(f"Error getting volumes for instance {instance['InstanceId']}: {e}")
                        
                        if 'User initiated' in instance_data['StopTime']:
                            try:
                                stop_time_str = instance_data['StopTime'].split('(')[1].split(')')[0]
                                stop_time = pd.to_datetime(stop_time_str)
                                instance_data['StoppedDays'] = (pd.Timestamp.now(tz=timezone.utc) - stop_time).total_seconds() / (24 * 3600)
                            except:
                                instance_data['StoppedDays'] = 0
                        else:
                            instance_data['StoppedDays'] = 0
                        
                        if instance_data['Age_Days'] >= age_threshold_days:
                            instances.append(instance_data)
                            
        except ClientError as e:
            self.logger.error(f"Error fetching stopped instances: {e}")
            return pd.DataFrame()

        df = pd.DataFrame(instances)
        if not df.empty:
            df['Age_Days'] = df['Age_Days'].round(2)
            df['StoppedDays'] = df['StoppedDays'].round(2)
            df['StorageCost'] = df['StorageCost'].round(2)

            # StorageCost is already monthly cost per GB
            df['MonthlyCost'] = df['StorageCost']
            df['YearlyCost'] = df['StorageCost'] * 12
            
            df['LaunchTime'] = pd.to_datetime(df['LaunchTime']).dt.strftime('%Y-%m-%d %H:%M:%S')
            
            df = df.sort_values('StorageCost', ascending=False)
            
            total_monthly_cost = df['MonthlyCost'].sum()
            total_storage = df['TotalStorageGB'].sum()
            
            summary_df = pd.DataFrame([{
                'TotalInstances': len(df),
                'TotalStorageGB': total_storage,
                'TotalMonthlyCost': total_monthly_cost,
                'TotalYearlyCost': total_monthly_cost * 12,
                'AvgInstanceAge': df['Age_Days'].mean(),
                'AvgStoppedDays': df['StoppedDays'].mean()
            }])
            
            return df, summary_df
        
        return pd.DataFrame(), pd.DataFrame()

    def save_stopped_instances_report(self, df: pd.DataFrame, summary_df: pd.DataFrame, name: str):
        if not df.empty:
            csv_path = f"{self.output_dir}/{name}.csv"
            df.to_csv(csv_path, index=False)
            
            md_path = f"{self.output_dir}/{name}.md"
            with open(md_path, 'w') as f:
                f.write(f"# {name.replace('_', ' ').title()}\n\n")
                f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                f.write("## Summary\n")
                f.write(f"- Total Stopped Instances: {summary_df['TotalInstances'].iloc[0]}\n")
                f.write(f"- Total Storage Used: {summary_df['TotalStorageGB'].iloc[0]:.2f} GB\n")
                f.write(f"- Total Monthly Cost: ${summary_df['TotalMonthlyCost'].iloc[0]:.2f}\n")
                f.write(f"- Total Yearly Cost: ${summary_df['TotalYearlyCost'].iloc[0]:.2f}\n")
                f.write(f"- Average Instance Age: {summary_df['AvgInstanceAge'].iloc[0]:.2f} days\n")
                f.write(f"- Average Time Stopped: {summary_df['AvgStoppedDays'].iloc[0]:.2f} days\n\n")
                
                f.write("## Detailed Instance List\n")
                f.write(df.to_markdown(index=False))

    def save_savings_summary(self, audit_results: Dict[str, pd.DataFrame]):
        """Generate and save savings summary including stopped instances."""
        summary = []
        total_monthly_savings = 0
        
        summary.append("# Cost Savings Summary\n")
        summary.append(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        

        if 'all_stopped_instances' in audit_results and not audit_results['all_stopped_instances'].empty:
            monthly_stopped_savings = audit_results['all_stopped_instances']['MonthlyCost'].sum()
            total_monthly_savings += monthly_stopped_savings
            total_storage = audit_results['all_stopped_instances']['TotalStorageGB'].sum()
            
            summary.append(f"\n## Stopped Instances Savings (if deleted)")
            summary.append(f"- Monthly Savings: ${monthly_stopped_savings:.2f}")
            summary.append(f"- Yearly Savings: ${monthly_stopped_savings * 12:.2f}")
            summary.append(f"- Number of Stopped Instances: {len(audit_results['all_stopped_instances'])}")
            summary.append(f"- Total Storage Being Paid For: {total_storage:.2f} GB")
            

            if 'old_stopped_instances' in audit_results and not audit_results['old_stopped_instances'].empty:
                old_monthly_savings = audit_results['old_stopped_instances']['MonthlyCost'].sum()
                old_storage = audit_results['old_stopped_instances']['TotalStorageGB'].sum()
                summary.append(f"\n### Old Stopped Instances (90+ days)")
                summary.append(f"- Monthly Savings: ${old_monthly_savings:.2f}")
                summary.append(f"- Yearly Savings: ${old_monthly_savings * 12:.2f}")
                summary.append(f"- Number of Old Stopped Instances: {len(audit_results['old_stopped_instances'])}")
                summary.append(f"- Storage Used by Old Instances: {old_storage:.2f} GB")
        

        if 'duplicate_snapshots' in audit_results and not audit_results['duplicate_snapshots'].empty:
            monthly_snapshot_savings = audit_results['duplicate_snapshots']['PotentialMonthlySavings'].sum()
            total_monthly_savings += monthly_snapshot_savings
            duplicate_count = len(audit_results['duplicate_snapshots'][audit_results['duplicate_snapshots']['IsNewest'] == False])
            total_size = audit_results['duplicate_snapshots'][audit_results['duplicate_snapshots']['IsNewest'] == False]['Size'].sum()
            
            summary.append(f"\n## Duplicate Snapshot Savings")
            summary.append(f"- Monthly Savings: ${monthly_snapshot_savings:.2f}")
            summary.append(f"- Yearly Savings: ${monthly_snapshot_savings * 12:.2f}")
            summary.append(f"- Duplicate Snapshots That Can Be Removed: {duplicate_count}")
            summary.append(f"- Total Size of Duplicate Snapshots: {total_size} GB")
        

        if 'top_gp2_instances' in audit_results and not audit_results['top_gp2_instances'].empty:
            monthly_gp2_savings = audit_results['top_gp2_instances']['MonthlySavings'].sum()
            total_monthly_savings += monthly_gp2_savings
            summary.append(f"\n## GP2 to GP3 Conversion Savings")
            summary.append(f"- Monthly Savings: ${monthly_gp2_savings:.2f}")
            summary.append(f"- Yearly Savings: ${monthly_gp2_savings * 12:.2f}")
            summary.append(f"- Total GP2 Storage: {audit_results['top_gp2_instances']['TotalGP2Storage'].sum()} GB")
            summary.append(f"- Number of Instances: {len(audit_results['top_gp2_instances'])}")
        

        if 'unused_elastic_ips' in audit_results and not audit_results['unused_elastic_ips'].empty:
            monthly_eip_savings = audit_results['unused_elastic_ips']['MonthlyCost'].sum()
            total_monthly_savings += monthly_eip_savings
            summary.append(f"\n## Unused Elastic IP Savings")
            summary.append(f"- Monthly Savings: ${monthly_eip_savings:.2f}")
            summary.append(f"- Yearly Savings: ${monthly_eip_savings * 12:.2f}")
            summary.append(f"- Number of unused IPs: {len(audit_results['unused_elastic_ips'])}")
        
        summary.append(f"\n## Total Potential Savings")
        summary.append(f"- Monthly: ${total_monthly_savings:.2f}")
        summary.append(f"- Yearly: ${total_monthly_savings * 12:.2f}")
        
        summary.append("\n## Recommendations by Priority")
        recommendations = []
        
        if 'old_stopped_instances' in audit_results and not audit_results['old_stopped_instances'].empty:
            old_monthly = audit_results['old_stopped_instances']['MonthlyCost'].sum()
            recommendations.append((
                "Delete old stopped instances (90+ days inactive)",
                old_monthly,
                f"Delete {len(audit_results['old_stopped_instances'])} stopped instances that haven't been used in over 90 days"
            ))
        
        if 'duplicate_snapshots' in audit_results and not audit_results['duplicate_snapshots'].empty:
            dup_monthly = audit_results['duplicate_snapshots']['PotentialMonthlySavings'].sum()
            duplicate_count = len(audit_results['duplicate_snapshots'][audit_results['duplicate_snapshots']['IsNewest'] == False])
            recommendations.append((
                "Remove duplicate snapshots",
                dup_monthly,
                f"Delete {duplicate_count} duplicate snapshots while keeping the newest copy"
            ))
        
        if 'top_gp2_instances' in audit_results and not audit_results['top_gp2_instances'].empty:
            gp2_monthly = audit_results['top_gp2_instances']['MonthlySavings'].sum()
            recommendations.append((
                "Convert GP2 volumes to GP3",
                gp2_monthly,
                f"Convert {len(audit_results['top_gp2_instances'])} instances from GP2 to GP3 storage"
            ))
        
        if 'unused_elastic_ips' in audit_results and not audit_results['unused_elastic_ips'].empty:
            eip_monthly = audit_results['unused_elastic_ips']['MonthlyCost'].sum()
            recommendations.append((
                "Release unused Elastic IPs",
                eip_monthly,
                f"Release {len(audit_results['unused_elastic_ips'])} unused Elastic IPs"
            ))
        
        recommendations.sort(key=lambda x: x[1], reverse=True)
        
        for i, (title, savings, desc) in enumerate(recommendations, 1):
            summary.append(f"\n{i}. {title}")
            summary.append(f"   - Monthly Savings: ${savings:.2f}")
            summary.append(f"   - Action: {desc}")
        
        with open(f"{self.output_dir}/savings_summary.md", 'w') as f:
            f.write('\n'.join(summary))

    def run_audit(self):
        """Run the complete audit."""
        self.logger.info("Starting AWS resource audit...")
        
        audit_results = {}
        
        try:
            self.logger.info("Getting all stopped instances...")
            all_stopped_df, all_stopped_summary = self.get_stopped_instances_cost(age_threshold_days=0)
            self.save_stopped_instances_report(all_stopped_df, all_stopped_summary, 'all_stopped_instances')
            audit_results['all_stopped_instances'] = all_stopped_df
            
            self.logger.info("Getting old stopped instances (90+ days)...")
            old_stopped_df, old_stopped_summary = self.get_stopped_instances_cost(age_threshold_days=90)
            self.save_stopped_instances_report(old_stopped_df, old_stopped_summary, 'old_stopped_instances')
            audit_results['old_stopped_instances'] = old_stopped_df
            
        except Exception as e:
            self.logger.error(f"Error analyzing stopped instances: {e}")
            audit_results['all_stopped_instances'] = pd.DataFrame()
            audit_results['old_stopped_instances'] = pd.DataFrame()

        try:
            self.logger.info("Getting oldest EC2 instances...")
            audit_results['oldest_instances'] = self.get_oldest_instances(200)
            self.save_to_files(audit_results['oldest_instances'], 'oldest_instances')
        except Exception as e:
            self.logger.error(f"Error getting oldest instances: {e}")
            audit_results['oldest_instances'] = pd.DataFrame()

        try:
            self.logger.info("Getting snapshot information...")
            audit_results['duplicate_snapshots'] = self.get_snapshots_with_duplicates()
            self.save_to_files(audit_results['duplicate_snapshots'], 'duplicate_snapshots')
        except Exception as e:
            self.logger.error(f"Error getting snapshot information: {e}")
            audit_results['duplicate_snapshots'] = pd.DataFrame()

        try:
            self.logger.info("Getting GP2 instance information...")
            audit_results['top_gp2_instances'] = self.get_top_gp2_instances()
            self.save_to_files(audit_results['top_gp2_instances'], 'top_gp2_instances')
        except Exception as e:
            self.logger.error(f"Error getting GP2 instance information: {e}")
            audit_results['top_gp2_instances'] = pd.DataFrame()

        try:
            self.logger.info("Getting Elastic IP information...")
            audit_results['unused_elastic_ips'] = self.get_unused_elastic_ips()
            self.save_to_files(audit_results['unused_elastic_ips'], 'unused_elastic_ips')
        except Exception as e:
            self.logger.error(f"Error getting Elastic IP information: {e}")
            audit_results['unused_elastic_ips'] = pd.DataFrame()

        try:
            self.save_savings_summary(audit_results)
            
            summary = []
            summary.append("# Stopped Instances Cost Analysis\n")
            summary.append(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            if not audit_results['all_stopped_instances'].empty:
                total_monthly = audit_results['all_stopped_instances']['MonthlyCost'].sum()
                total_storage = audit_results['all_stopped_instances']['TotalStorageGB'].sum()
                total_instances = len(audit_results['all_stopped_instances'])
                
                summary.append("\n## All Stopped Instances")
                summary.append(f"- Total Stopped Instances: {total_instances}")
                summary.append(f"- Total Storage Used: {total_storage:.2f} GB")
                summary.append(f"- Monthly Cost: ${total_monthly:.2f}")
                summary.append(f"- Yearly Cost: ${total_monthly * 12:.2f}")
            
            if not audit_results['old_stopped_instances'].empty:
                old_monthly = audit_results['old_stopped_instances']['MonthlyCost'].sum()
                old_storage = audit_results['old_stopped_instances']['TotalStorageGB'].sum()
                old_instances = len(audit_results['old_stopped_instances'])
                
                summary.append("\n## Old Stopped Instances (90+ days)")
                summary.append(f"- Total Old Stopped Instances: {old_instances}")
                summary.append(f"- Total Storage Used: {old_storage:.2f} GB")
                summary.append(f"- Monthly Cost: ${old_monthly:.2f}")
                summary.append(f"- Yearly Cost: ${old_monthly * 12:.2f}")
            
            with open(f"{self.output_dir}/stopped_instances_summary.md", 'w') as f:
                f.write('\n'.join(summary))
                
            self.logger.info("Saved stopped instances summary")
        except Exception as e:
            self.logger.error(f"Error saving stopped instances summary: {e}")

        self.logger.info(f"Audit complete! Files saved in {self.output_dir}/")
        return audit_results


if __name__ == "__main__":
    auditor = AWSResourceAuditor()
    auditor.run_audit()
