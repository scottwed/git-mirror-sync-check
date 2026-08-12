import os
import smtplib
from email.message import EmailMessage

from loguru import logger

ENV_VARNAME_EMAIL_PASSWORD = 'MSC_EMAIL_PASSWORD'

class EmailSender:
    def __init__(self, yaml_data: dict):
        self.smtp_server:str = yaml_data["smtp"]["server"]
        self.smtp_port:int  = int(yaml_data["smtp"]["port"])
        self.sender_email:str  = yaml_data["email"]["sender"]
        self.receiver_email:str  = yaml_data["email"]["receiver"]
        self.subject_prefix:str  = yaml_data["email"]["subject_prefix"]

        if not os.environ.get(ENV_VARNAME_EMAIL_PASSWORD):
            logger.warning(f"Environment variable {ENV_VARNAME_EMAIL_PASSWORD} is not set.")


    def send(self, subject: str, body: str) -> bool:
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
