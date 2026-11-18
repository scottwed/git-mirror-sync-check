from pathlib import Path

import yaml
from loguru import logger

from notifier_email import EmailSender
from util import validate_input_file_path


class ConfigManager:
    def __init__(self, config_path: Path):
        self.problems: list[str] = []
        self.project_paths: list[str] = []
        self.mirror_hosts: list[str] = []

        with open(config_path, "r", encoding='utf-8') as file:
            yaml_data = yaml.safe_load(file)

            _monitor = yaml_data.get('monitor', {})
            if not _monitor:
                self.problems.append(' missing or empty top section "monitor"')
                return
            self.primary_fqdn: str = _monitor.get('primary_repo_fqdn', '')
            if not self.primary_fqdn:
                self.problems.append('missing or blank field: monitor.mirror_rr_fqdn')
            else:
                logger.info("Primary repo FQDN: {}", self.primary_fqdn)

            self.mirror_rr_fqdn: str = _monitor.get('mirror_rr_fqdn')
            if not self.mirror_rr_fqdn:
                self.problems.append('missing or blank field: monitor.mirror_rr_fqdn')
            else:
                logger.info("Mirror round-robin FQDN: {}", self.mirror_rr_fqdn)

            self.max_poll_freq_secs: int = int(_monitor.get('max_repo_polling_frequency_seconds', 0))
            if not self.max_poll_freq_secs:
                self.problems.append('missing or blank field: monitor.max_repo_polling_frequency_seconds')
            else:
                logger.info("Using maximum polling frequency of {} seconds", self.max_poll_freq_secs)

            if not _monitor.get('file_repo_paths'):
                self.problems.append('missing or blank field: monitor.file_repo_paths')
            else:
                self.projects_file_path: Path = Path(_monitor.get('file_repo_paths', ''))
                invalid_message = validate_input_file_path(self.projects_file_path, '.txt')
                if invalid_message:
                    self.problems.append(invalid_message)
                else:
                    with open(self.projects_file_path, 'r', encoding='utf-8') as f:
                        self.project_paths.extend([l.strip() for l in f.readlines() if l.strip() and not l.startswith('#')])
                        logger.info('Will monitor these repo projects: {}', self.project_paths)

            if not _monitor.get('file_mirror_hosts'):
                self.problems.append('missing or blank field: monitor.file_mirror_hosts')
            else:
                self.mirrors_file_path: Path = Path(_monitor.get('file_mirror_hosts'))
                invalid_message = validate_input_file_path(self.mirrors_file_path, '.txt')
                if invalid_message:
                    self.problems.append(invalid_message)
                else:
                    with open(self.mirrors_file_path, 'r', encoding='utf-8') as f:
                        self.mirror_hosts.extend([l.strip() for l in f.readlines() if l.strip() and not l.startswith('#')])
                        logger.info('Will monitor these mirror hosts: {}', self.mirror_hosts)

            self.email_notifier = EmailSender(yaml_data)
