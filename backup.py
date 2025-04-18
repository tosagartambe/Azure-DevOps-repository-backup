import os
import subprocess
import requests
import logging
import json
import argparse
from datetime import datetime
from requests.auth import HTTPBasicAuth
from typing import List, Dict, Set
from azure.storage.blob import BlobServiceClient
import boto3
from dotenv import load_dotenv
import smtplib
from email.message import EmailMessage
from email.utils import formatdate


load_dotenv()
# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class AzureDevOpsBackup:
    def __init__(
        self,
        organization: str,
        pat_token: str,
        excluded_projects: Set[str] = None,
        azure_backup: bool = False,
        aws_backup: bool = False,
        dry_run: bool = False,
        keep_local: bool = False

    ):
        self.organization = organization
        self.pat_token = pat_token
        self.auth = HTTPBasicAuth('', pat_token)
        self.base_url = f"https://dev.azure.com/{organization}"
        self.excluded_projects = excluded_projects or set()
        self.azure_backup = azure_backup
        self.aws_backup = aws_backup
        self.dry_run = dry_run
        self.keep_local = keep_local
        self.manifest: List[Dict[str, str]] = []

        # Timestamp + backup folder
        self.timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
        self.backup_root = os.path.join(os.getcwd(), "backups", self.timestamp)
        os.makedirs(self.backup_root, exist_ok=True)

        logger.info(f"📂 Created backup folder: {self.backup_root}")
        print(f"📂 Backup root: {self.backup_root}")

        if self.excluded_projects:
            print(f"🚫 Excluding projects: {', '.join(self.excluded_projects)}")

        # Azure Blob setup
        if self.azure_backup:
            try:
                conn_str = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
                self.azure_blob_service = BlobServiceClient.from_connection_string(conn_str)
                self.azure_container = os.environ["AZURE_CONTAINER"]
            except Exception as e:
                logger.error(f"❌ Azure Blob setup failed: {e}")
                self.azure_backup = False

        # AWS S3 setup
        if self.aws_backup:
            try:
                self.aws_s3_client = boto3.client("s3")
                self.aws_bucket = os.environ["AWS_BUCKET"]
            except Exception as e:
                logger.error(f"❌ AWS S3 setup failed: {e}")
                self.aws_backup = False

    def get_projects(self) -> List[str]:
        logger.info("📡 Fetching projects...")
        url = f"{self.base_url}/_apis/projects?api-version=7.0"
        try:
            response = requests.get(url, auth=self.auth)
            response.raise_for_status()
            data = response.json()
            projects = [p["name"] for p in data.get("value", []) if p["name"] not in self.excluded_projects]
            logger.info(f"✅ Found {len(projects)} project(s) after exclusions")
            return projects
        except requests.RequestException as e:
            logger.error(f"❌ Failed to fetch projects: {e}")
            return []

    def get_repos_by_project(self, project: str) -> List[Dict[str, str]]:
        logger.info(f"🔍 Fetching repos for project: {project}")
        url = f"{self.base_url}/{project}/_apis/git/repositories?api-version=7.0"
        try:
            response = requests.get(url, auth=self.auth)
            response.raise_for_status()
            data = response.json()
            return [
                {
                    "name": repo["name"],
                    "clone_url": repo["remoteUrl"]
                }
                for repo in data.get("value", [])
            ]
        except requests.RequestException as e:
            logger.error(f"❌ Failed to fetch repos for {project}: {e}")
            return []

    def upload_backup(self, zip_file_path: str) -> None:
        """
        Uploads backup zip file to Azure Blob and AWS S3 using local folder structure like:
        backups/<timestamp>/<project>-<timestamp>/<zip>.zip → cloud/<timestamp>/<project>-<timestamp>/<zip>.zip
        """
        # Root folder for all backups
        backup_base_root = os.path.dirname(self.backup_root)  # '.../backups'

        # Get path relative to /backups/ instead of /backups/<timestamp>
        relative_path = os.path.relpath(zip_file_path, backup_base_root)

        # Cloud-safe path (forward slashes)
        cloud_path = relative_path.replace(os.sep, "/")

        if self.dry_run:
            logger.info(f"🧪 [Dry Run] Skipping upload: {cloud_path}")
            return

        if not self.azure_backup and not self.aws_backup:
            logger.info(f"☁️ Cloud backup disabled. Skipping upload for: {cloud_path}")
            return

        logger.info(f"📤 Uploading backup: {cloud_path}")

        if self.azure_backup:
            try:
                blob_client = self.azure_blob_service.get_blob_client(
                    container=self.azure_container,
                    blob=cloud_path
                )
                with open(zip_file_path, "rb") as data:
                    blob_client.upload_blob(data, overwrite=True)
                logger.info(f"☁️ Uploaded to Azure Blob: {cloud_path}")
            except Exception as e:
                logger.error(f"❌ Azure upload failed for {cloud_path}: {e}")

        if self.aws_backup:
            try:
                self.aws_s3_client.upload_file(zip_file_path, self.aws_bucket, cloud_path)
                logger.info(f"🌩️ Uploaded to AWS S3: {cloud_path}")
            except Exception as e:
                logger.error(f"❌ AWS upload failed for {cloud_path}: {e}")



    def backup_repo(self, project: str, repo: Dict[str, str], project_dir: str) -> None:
        repo_name = repo["name"]
        clone_url = repo["clone_url"]

        repo_path_parts = clone_url.split(f"/{self.organization}/")
        repo_path = f"/{self.organization}/{repo_path_parts[1]}" if len(repo_path_parts) > 1 else f"/{self.organization}/{project}/_git/{repo_name}"
        pat_clone_url = f"https://:{self.pat_token}@dev.azure.com{repo_path}"

        temp_clone_path = os.path.join(project_dir, f"{repo_name}.git")
        zip_file_name = f"{project}-{repo_name}-{self.timestamp}.zip"
        zip_file_path = os.path.join(project_dir, zip_file_name)

        logger.info(f"📦 Repo: {repo_name} → {zip_file_name}")

        # Add to manifest
        self.manifest.append({
            "project": project,
            "repo": repo_name,
            "zip_file": zip_file_name,
            "path": zip_file_path,
        })

        if self.dry_run:
            logger.info("🧪 [Dry Run] Skipping clone and zip.")
            return

        try:
            subprocess.run(["git", "clone", "--mirror", pat_clone_url, temp_clone_path], check=True)
            subprocess.run(["zip", "-r", zip_file_path, temp_clone_path], check=True)
            logger.info(f"✅ Backup done: {zip_file_path}")
            self.upload_backup(zip_file_path)
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to backup {project}/{repo_name}: {e}")
        finally:
            if os.path.exists(temp_clone_path):
                subprocess.run(["rm", "-rf", temp_clone_path])

    def run_backup(self):
        success = True
        error_message = ""

        try:
            projects = self.get_projects()
            if not projects:
                logger.warning("⚠️ No projects to back up.")
                success = False
                error_message = "No projects found."
                return

            for project in projects:
                project_dir = os.path.join(self.backup_root, f"{project}-{self.timestamp}")
                os.makedirs(project_dir, exist_ok=True)
                print(f"📁 Created folder: {project_dir}")

                repos = self.get_repos_by_project(project)
                if not repos:
                    print(f"⚠️ No repos found in {project}")
                    continue

                for repo in repos:
                    print(f"📥 Backing up: {project}/{repo['name']}")
                    self.backup_repo(project, repo, project_dir)

            self.write_manifest()

        except Exception as e:
            success = False
            error_message = str(e)
            logger.exception("❌ Exception occurred during backup:")

        finally:
            # Always attempt email (success or failure)
            self.send_email_notification(success=success, error_message=error_message)

            if success:
                self.delete_local_backup_folder()


    def write_manifest(self):
        manifest_file = os.path.join(self.backup_root, f"manifest-{self.timestamp}.json")
        content = {
            "organization": self.organization,
            "timestamp": self.timestamp,
            "repos": self.manifest
        }

        with open(manifest_file, "w") as f:
            json.dump(content, f, indent=2)

        logger.info(f"📝 Backup manifest written: {manifest_file}")

    def delete_local_backup_folder(self):
        """
        Deletes the local backup folder after successful run.
        Only runs when dry_run is False.
        """
        if self.dry_run:
            logger.info("🧪 [Dry Run] Skipping deletion of local backup folder.")
            return
        
        if self.keep_local:
            logger.info("--keep-local enabled. Local backup folder will be retained.")
            return

        try:
            logger.info(f"🧹 Deleting local backup folder: {self.backup_root}")
            subprocess.run(["rm", "-rf", self.backup_root], check=True)
            logger.info("✅ Local backup folder deleted successfully.")
        except Exception as e:
            logger.error(f"❌ Failed to delete local backup folder: {e}")

    def send_email_notification(self, success: bool, error_message: str = ""):
        """
        Sends an email notification about backup result, and attaches the manifest.
        """
        logger.info("📧 Preparing to send backup status email...")

        subject = f"[Azure DevOps Backup] {'✅ Success' if success else '❌ Failed'} - {self.organization} @ {self.timestamp}"
        from_email = os.getenv("EMAIL_FROM")
        to_emails = os.getenv("EMAIL_TO", "").split(",")
        manifest_file = os.path.join(self.backup_root, f"manifest-{self.timestamp}.json")

        body_lines = [
            f"🕒 Timestamp: {self.timestamp}",
            f"🏢 Organization: {self.organization}",
            f"📦 Total Repos: {len(self.manifest)}",
            f"☁️ Azure Upload: {'Yes' if self.azure_backup else 'No'}",
            f"☁️ AWS Upload: {'Yes' if self.aws_backup else 'No'}",
        ]

        if success:
            body_lines.insert(0, "✅ Backup completed successfully.")
        else:
            body_lines.insert(0, "❌ Backup FAILED.")
            if error_message:
                body_lines.append("")
                body_lines.append("💥 Error Details:")
                body_lines.append(error_message)

        body = "\n".join(body_lines)

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = ", ".join([email.strip() for email in to_emails])
        msg["Date"] = formatdate(localtime=True)
        msg.set_content(body)

        # Attach manifest file if exists
        if os.path.exists(manifest_file):
            try:
                with open(manifest_file, "rb") as f:
                    manifest_data = f.read()
                msg.add_attachment(
                    manifest_data,
                    maintype="application",
                    subtype="json",
                    filename=f"manifest-{self.timestamp}.json"
                )
                logger.info("📎 Manifest attached to email.")
            except Exception as e:
                logger.warning(f"⚠️ Failed to attach manifest: {e}")

        try:
            smtp_server = os.getenv("SMTP_SERVER")
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
            smtp_username = os.getenv("SMTP_USERNAME")
            smtp_password = os.getenv("SMTP_PASSWORD")

            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.send_message(msg, from_addr=from_email, to_addrs=to_emails)
                logger.info(f"📬 Email sent to {to_emails}")
        except Exception as e:
            logger.error(f"❌ Failed to send email: {e}")



def main():
    parser = argparse.ArgumentParser(
        description="🛡️ Azure DevOps Git Repo Backup Tool (Local + Optional Cloud Upload)"
    )
    parser.add_argument("--org", "--organization", dest="organization", required=True, help="Azure DevOps organization name")
    parser.add_argument("--azure-backup", action="store_true", help="Upload backups to Azure Blob")
    parser.add_argument("--aws-backup", action="store_true", help="Upload backups to AWS S3")
    parser.add_argument("--dry-run", action="store_true", help="Simulate backup without cloning/zipping/uploading")
    parser.add_argument("--exclude-project", action="append", help="Project to exclude (can be used multiple times)")
    parser.add_argument("--keep-local", action="store_true", help="Retain local backup folder after uploading")


    args = parser.parse_args()

    pat_token = os.getenv("AZURE_DEVOPS_PAT")
    if not pat_token:
        print("❌ Environment variable AZURE_DEVOPS_PAT is not set.")
        return

    excluded_projects = set(args.exclude_project or [])

    print("🔧 Config:")
    print(f" - Org: {args.organization}")
    print(f" - Azure Backup: {args.azure_backup}")
    print(f" - AWS Backup: {args.aws_backup}")
    print(f" - Dry Run: {args.dry_run}")
    print(f" - Keep Local: {args.keep_local}")
    if excluded_projects:
        print(f" - Excluded Projects: {', '.join(excluded_projects)}")

    backup = AzureDevOpsBackup(
        organization=args.organization,
        pat_token=pat_token,
        excluded_projects=excluded_projects,
        azure_backup=args.azure_backup,
        aws_backup=args.aws_backup,
        dry_run=args.dry_run,
        keep_local=args.keep_local
    )

    backup.run_backup()


if __name__ == "__main__":
    main()
