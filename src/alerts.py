from mirror_health import GitMirrorHealth
from notifier_email import EmailSender
from util import calc_ss_diff


def process_alert_rules(repos_for_project: list[GitMirrorHealth], notifier: EmailSender) -> None:
    #  Alert on up=0 for > x minutes, git_port_open=0 > x minutes, in_service=0 > 26 hours
    subject, body = rule_error_accumulation(repos_for_project, threshold=2)
    if subject and body:
        notifier.send(subject, body)
    return


def rule_error_accumulation(repos_for_project: list[GitMirrorHealth], threshold:int=2) -> tuple[str, str]:
    # Generates an alert when one or more mirror hosts for a git project have more enough consecutive errors to
    # meet or exceed the threshold parameter.  The body will contain a summary of problems across all mirrors

    max_error_count = max([ghm.sync_errors_total for ghm in repos_for_project])
    if max_error_count >= threshold:
        primary_ghm = repos_for_project[0]
        project_name = primary_ghm.project
        subject = f'project {project_name} has reached error threshold of ({max_error_count} / {threshold})'
        content = []
        for ghm in repos_for_project:
            if ghm.sync_errors_total:
                discrepancy = calc_ss_diff(primary_ghm.index_snapshot, ghm.index_snapshot)
                content.append(f'')



    # discrepancy = calc_ss_diff(primary_ghm.index_snapshot, ghm.index_snapshot)
    return '', ''