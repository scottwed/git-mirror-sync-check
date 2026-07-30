from mirror_health import GitMirrorHealth
from notifier_email import EmailSender
from util import calc_ss_unique


def process_alert_rules(repos_for_project: list[GitMirrorHealth], notifier: EmailSender) -> None:
    #  Alert on up=0 for > x minutes, git_port_open=0 > x minutes, in_service=0 > 26 hours
    subject, message = rule_error_accumulation(repos_for_project, threshold=2)
    if subject and message:
        notifier.send(subject, message)
    return


def rule_error_accumulation(repos_for_project: list[GitMirrorHealth], threshold:int=2) -> tuple[str, str]:
    # Generates an alert when one or more mirror hosts for a git project have more enough consecutive errors to
    # meet or exceed the threshold parameter.  The body will contain a summary of problems across all mirrors

    max_error_count = max([ghm.sync_errors_total for ghm in repos_for_project])
    if max_error_count >= threshold:
        primary_ghm = repos_for_project[0]
        project_name = primary_ghm.project
        subject = (f'project {project_name} has met error threshold of '
                   f'{max_error_count} (highest) / {threshold} (allowed)')
        content = []
        for ghm in repos_for_project:
            if ghm.sync_errors_total:
                discrepancy = calc_ss_unique(primary_ghm.index_snapshot, ghm.index_snapshot)
                content.append(f'-----\n'
                               f'Primary: {primary_ghm.instance} ({primary_ghm.ip_address}), '
                               f'primary_sync_time={primary_ghm.last_in_sync.isoformat(timespec="seconds")}, '
                               f'unique:\n{discrepancy[0]}\n\n'
                               f'Mirror: {ghm.instance} ({ghm.ip_address}), last_in_sync={ghm.last_in_sync.isoformat(timespec="seconds")}, '
                               f'errors={ghm.sync_errors_total}, unique:\n{discrepancy[1]}\n'
                               f'-----')
        return subject, '\n\n'.join(content)

    return '', ''