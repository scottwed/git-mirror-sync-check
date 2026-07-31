import os
import smtplib
from email.message import EmailMessage

from loguru import logger
import yaml

ENV_VARNAME_EMAIL_PASSWORD = 'MSC_EMAIL_PASSWORD'

class EmailSender:
    """ Email sender is initialized via a YAML config file (see below).

    smtp:
      server: "smtp.replace.me.com"
      port: 587
    email:
      sender: "mirror_health@replace.me.com"
      receiver: "admin@replace.me.com"
      subject_prefix: "Desired prefix for alert notifications:"
    """

    def __init__(self, config_path: str):
        # Load configuration from YAML
        with open(config_path, "r", encoding='utf-8') as file:
            self.config = yaml.safe_load(file)

        # Extract SMTP and email metadata
        self.smtp_server:str = self.config["smtp"]["server"]
        self.smtp_port:int  = int(self.config["smtp"]["port"])
        self.sender_email:str  = self.config["email"]["sender"]
        self.receiver_email:str  = self.config["email"]["receiver"]
        self.subject_prefix:str  = self.config["email"]["subject_prefix"]

        # Securely fetch password from environment variables
        if not os.environ.get(ENV_VARNAME_EMAIL_PASSWORD):
            raise ValueError(f"Environment variable {ENV_VARNAME_EMAIL_PASSWORD} is not set.")


    def send(self, subject: str, body: str) -> bool:
        """Sends an email message using the persistent configurations."""
        msg = EmailMessage()
        msg["From"] = self.sender_email
        msg["To"] = self.receiver_email
        msg["Subject"] = f'{self.subject_prefix} {subject}'
        msg.set_content(body)

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, password=os.environ.get(ENV_VARNAME_EMAIL_PASSWORD, ''))
                server.send_message(msg)
            logger.info('Email successfully sent to {}', self.receiver_email)
            return True
        except Exception as e:
            logger.error('Failed to send email: {}', e)
            return False
