# 🛡️ Azure DevOps Git Repository Backup Tool

Automate secure backups of **all Git repositories** across **Azure DevOps projects**, with optional upload to:

- ☁️ **Azure Blob Storage**
- ☁️ **AWS S3**

Includes features like:

- 🔐 Personal Access Token (PAT) authentication
- 🧪 `--dry-run` mode
- 📎 Manifest JSON generation
- ✉️ Email notifications (with manifest attached)
- 🧹 Optional local backup cleanup

---

## 📦 Features

- ✅ Backs up all Git repositories in your Azure DevOps organization
- ✅ Uploads backups to Azure Blob / AWS S3 (folder structure preserved)
- ✅ Exclude specific projects via `--exclude-project`
- ✅ Generates `manifest.json` for auditing
- ✅ Sends email notifications (with success/failure and manifest attached)
- ✅ Supports `.env` for secrets and SMTP config
- ✅ Built-in `--dry-run` and `--keep-local` flags

---

## 📁 Folder Structure

Local backup is stored as:

```
  backups/ 
  ├── 20250418-1455/ 
  │    └── ProjectName-20250418-1455/ 
  │    │    ├── ProjectName-Repo1-20250418-1455.zip 
  │    │    └── ProjectName-Repo2-20250418-1455.zip
  │    └── Project2-20250418-1455/
  │         ├── Project2-Repo1-20250418-1455.zip
  │         └── Project2-Repo2-20250418-1455.zip
  └── manifest-20250418-1455.json

```


Cloud structure (Azure or S3) mirrors this.

---

## ⚙️ Requirements

- Python 3.8+
- Git CLI
- Installed Python packages:

```bash
pip install -r requirements.txt
```

## 🔐 Environment Setup
Create a .env file in the project root:
```bash
AZURE_DEVOPS_PAT=""
AZURE_STORAGE_CONNECTION_STRING=""
AWS_ACCESS_KEY_ID=""
AWS_SECRET_ACCESS_KEY=""
AWS_DEFAULT_REGION=""
AZURE_CONTAINER=""
AWS_BUCKET=""

EMAIL_FROM="user@example.com"
EMAIL_TO="user1@example.com,user2@example.com" # Can be used comma separed multiple emails
SMTP_SERVER="smtp.example.com"
SMTP_PORT="587"
SMTP_USERNAME="user@example.com"
SMTP_PASSWORD="your-smtp-password"  # Use app password for Gmail
```
## 🚀 Usage
```bash
python backup.py --org <your-org-name> [flags...]
```
## 🧾 Example
```bash
python backup.py \
  --org my-ado-org \
  --azure-backup \
  --aws-backup \
  --exclude-project "Internal Tools" \
  --exclude-project "Legacy Repos" \
  --keep-local \
  --dry-run 
```
## 🛠️ Flags

| Flag                |         Description                                  |
| ---                 | ---                                                  |
| `--org`             | Required. Azure DevOps organization name             |
| `--azure-backup`    | Upload backups to Azure Blob                         |
| `--aws-backup`      | Upload backups to AWS S3                             |
| `--dry-run`         | Simulate full run without clone/zip/upload           |
| `--exclude-project` | Can be used multiple times to skip specific projects |
| `--keep-local`      | Retain local backup folder after upload              |


## ✉️ Email Notifications
Every run ends with an email notification including:

✅ Backup summary

📝 Attached manifest.json

❌ Error log (if backup failed)

Supports multiple recipients via comma-separated list in `EMAIL_TO`.

## 🔄 Automation Tips
🕒 Schedule via Azure DevOps Pipeline
Use YAML pipeline

Install dependencies via requirements.txt

Set env vars from secrets library

Schedule every X hours with cron trigger

🐧 Linux Cron Job Example
```bash
0 * * * * cd /path/to/script && /usr/bin/python3 backup.py --org my-org --azure-backup --aws-backup --exclude-project "project1" --exclude-project "project2" --keep-local
```

## 🧪 Testing
`--dry-run`: Confirm which repos would be backed up, without touching anything

Invalid PAT or no internet? You'll see detailed logs and email error

## 📎 Manifest Example
```bash
{
  "organization": "my-org",
  "timestamp": "20250418-1500",
  "repos": [
    {
      "project": "MyProject",
      "repo": "MyRepo",
      "zip_file": "MyProject-MyRepo-20250418-1500.zip",
      "path": "/backups/20250418-1500/MyProject-20250418-1500/MyProject-MyRepo-20250418-1500.zip"
    }
  ]
}

```
## 🧹 Cleanup Policy
By default, local backup folder is deleted after successful upload

Use `--keep-local` to override

## 🧯 Troubleshooting
|Issue | Fix |
|---  | --- |
|535 SMTP error | You're likely using a Gmail password. Use an App Password instead |
|Nothing uploads to cloud | Check your .env for valid connection string / bucket names |
|Email not sent | Missing env vars or incorrect SMTP credentials |
|AZURE_DEVOPS_PAT error | PAT expired or missing. Renew with correct scopes (read Git + project info)|


