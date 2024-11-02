# AWS Cost Optimizer & Resource Auditor 

Zero-configuration AWS cost optimization tool. Just run and get comprehensive cost-saving insights instantly!

## 🎯 Quick Start

### As a Module
```python
# Just two lines to get all insights:
from aws_resource_auditor import AWSResourceAuditor
AWSResourceAuditor().run_audit()
```

### As a Script
```bash
# Direct script execution
python aws_resource_auditor.py

# Or make it executable
chmod +x aws_resource_auditor.py
./aws_resource_auditor.py
```

## 💡 Key Features
- Zero configuration required
- Automatic resource discovery
- Comprehensive cost analysis
- Detailed savings recommendations
- Age-based resource analysis
- Duplicate resource detection
- CSV and Markdown reports

## Prerequisites
- Python 3.7+
- boto3
- pandas
- AWS credentials configured (default profile or environment variables)

## Installation
```bash
pip install boto3 pandas
```

## 📊 Sample Reports

### Cost Savings Summary
```markdown
# Cost Savings Summary
Generated on: 2024-11-02 15:30:45

## Stopped Instances Savings (if deleted)
- Monthly Savings: $165.00
- Yearly Savings: $1,980.00
- Number of Stopped Instances: 12
- Total Storage Being Paid For: 2,150 GB

### Old Stopped Instances (90+ days)
- Monthly Savings: $95.00
- Yearly Savings: $1,140.00
- Number of Old Stopped Instances: 7
- Storage Used by Old Instances: 1,250 GB

## Duplicate Snapshot Savings
- Monthly Savings: $175.00
- Yearly Savings: $2,100.00
- Duplicate Snapshots That Can Be Removed: 45
- Total Size of Duplicate Snapshots: 3,500 GB

## GP2 to GP3 Conversion Savings
- Monthly Savings: $124.00
- Yearly Savings: $1,488.00
- Total GP2 Storage: 6,200 GB
- Number of Instances: 23

## Unused Elastic IP Savings
- Monthly Savings: $21.90
- Yearly Savings: $262.80
- Number of unused IPs: 6

## Total Potential Savings
- Monthly: $485.90
- Yearly: $5,830.80

## Recommendations by Priority
1. Delete old stopped instances (90+ days)
   - Monthly Savings: $95.00
   - Action: Delete 7 stopped instances that haven't been used in over 90 days

2. Remove duplicate snapshots
   - Monthly Savings: $175.00
   - Action: Delete 45 duplicate snapshots while keeping the newest copy

3. Convert GP2 volumes to GP3
   - Monthly Savings: $124.00
   - Action: Convert 23 instances from GP2 to GP3 storage

4. Release unused Elastic IPs
   - Monthly Savings: $21.90
   - Action: Release 6 unused Elastic IPs
```

### Detailed Resource Reports

#### 1. Stopped Instances Cost Report
```markdown
| InstanceId     | Name          | Age_Days | StoppedDays | TotalStorageGB | MonthlyCost |
|---------------|---------------|----------|-------------|----------------|-------------|
| i-0abc123def  | prod-db-1     | 456.2    | 123.5       | 500           | $50.00      |
| i-0def456ghi  | test-app-2    | 234.1    | 89.3        | 200           | $20.00      |
| i-0ghi789jkl  | dev-service-3 | 567.8    | 234.6       | 100           | $10.00      |
| i-0jkl012mno  | stage-api-1   | 345.2    | 178.9       | 300           | $30.00      |
| i-0mno345pqr  | qa-server-2   | 432.1    | 156.7       | 150           | $15.00      |
| i-0pqr678stu  | backup-db-1   | 678.9    | 345.2       | 400           | $40.00      |
```

#### 2. Oldest Instances Report
```markdown
| InstanceId     | Name           | LaunchTime         | Age_Days | State   | InstanceType |
|---------------|----------------|-------------------|----------|---------|--------------|
| i-0123abc456  | legacy-app-1   | 2020-03-15 08:30  | 1423.5   | running | t3.medium    |
| i-0456def789  | old-batch-2    | 2020-06-22 14:15  | 1324.2   | stopped | c5.large     |
| i-0789ghi012  | archive-db-1   | 2020-09-10 11:45  | 1223.7   | running | r5.xlarge    |
| i-0012jkl345  | monitor-old-1  | 2021-01-05 09:20  | 1105.3   | running | t3.large     |
| i-0345mno678  | legacy-auth-2  | 2021-03-20 16:10  | 1031.8   | stopped | t3.xlarge    |
| i-0678pqr901  | backup-old-1   | 2021-06-15 13:25  | 944.6    | running | t3.small     |
```

#### 3. GP2 to GP3 Conversion Opportunities
```markdown
| InstanceId     | Name          | TotalGP2Storage | VolumeCount | MonthlySavings |
|---------------|---------------|-----------------|-------------|----------------|
| i-0abc123def  | prod-db-1     | 2000           | 4           | $40.00         |
| i-0def456ghi  | analytics-2   | 1500           | 3           | $30.00         |
| i-0ghi789jkl  | warehouse-1   | 1000           | 2           | $20.00         |
| i-0jkl012mno  | elastic-1     | 800            | 2           | $16.00         |
| i-0mno345pqr  | cache-master  | 500            | 1           | $10.00         |
| i-0pqr678stu  | mongo-1       | 400            | 1           | $8.00          |
```

#### 4. Duplicate Snapshots
```markdown
| SnapshotId      | VolumeId      | Size (GB) | Age_Days | PotentialSavings |
|-----------------|---------------|-----------|----------|------------------|
| snap-0abc123def | vol-0123abcd  | 500       | 45.2     | $25.00          |
| snap-0def456ghi | vol-0123abcd  | 500       | 32.5     | $25.00          |
| snap-0ghi789jkl | vol-4567efgh  | 1000      | 89.7     | $50.00          |
| snap-0jkl012mno | vol-4567efgh  | 1000      | 67.3     | $50.00          |
| snap-0mno345pqr | vol-89ijklmn  | 250       | 123.4    | $12.50          |
| snap-0pqr678stu | vol-89ijklmn  | 250       | 98.6     | $12.50          |
```

#### 5. Unused Elastic IPs
```markdown
| PublicIp      | AllocationId  | Domain | MonthlyCost |
|---------------|---------------|--------|-------------|
| 52.1.2.3      | eipalloc-123 | vpc    | $3.65       |
| 52.4.5.6      | eipalloc-456 | vpc    | $3.65       |
| 52.7.8.9      | eipalloc-789 | vpc    | $3.65       |
| 52.10.11.12   | eipalloc-abc | vpc    | $3.65       |
| 52.13.14.15   | eipalloc-def | vpc    | $3.65       |
| 52.16.17.18   | eipalloc-ghi | vpc    | $3.65       |
```

## 📁 Output Directory Structure
```
aws_audit_20241102_153045/
├── audit.log
├── savings_summary.md
├── stopped_instances_summary.md
├── all_stopped_instances.csv
├── all_stopped_instances.md
├── old_stopped_instances.csv
├── old_stopped_instances.md
├── oldest_instances.csv
├── oldest_instances.md
├── duplicate_snapshots.csv
├── duplicate_snapshots.md
├── top_gp2_instances.csv
├── top_gp2_instances.md
├── unused_elastic_ips.csv
└── unused_elastic_ips.md
```

## 🔒 Required AWS Permissions
Minimum IAM policy required:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:Describe*",
                "pricing:GetProducts"
            ],
            "Resource": "*"
        }
    ]
}
```

## 🛠 Advanced Usage
```python
auditor = AWSResourceAuditor()

# Get specific reports
stopped_instances, summary = auditor.get_stopped_instances_cost()
oldest_instances = auditor.get_oldest_instances(200)
duplicate_snaps = auditor.get_snapshots_with_duplicates()
gp2_instances = auditor.get_top_gp2_instances()
unused_eips = auditor.get_unused_elastic_ips()

# Custom age threshold for old instances
old_stopped, old_summary = auditor.get_stopped_instances_cost(age_threshold_days=180)
```

## 🐛 Troubleshooting
1. Ensure AWS credentials are properly configured
2. Check region settings in AWS config
3. Verify IAM permissions
4. Review audit.log for detailed error messages

## 🔄 Regular Monitoring
Consider setting up a cron job to run the audit regularly:
```bash
0 0 * * 0 /usr/bin/python3 /path/to/aws_resource_auditor.py
```

## 🤝 Contributing
Pull requests welcome! For major changes, please open an issue first.

## 📜 License
MIT

## 📫 Support
For issues and feature requests, please create a GitHub issue.