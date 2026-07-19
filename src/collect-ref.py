

# References
# git ls-remote git://git.git.savannah.gnu.org/test-project.git
# git ls-remote git://92.118.206.28/test-project.git
# https://git-scm.com/docs/git-ls-remote
# https://confluence.atlassian.com/bitbucketserverkb/informational-about-bitbucket-smart-mirrors-1416822816.html

# Sample
repo_ipa = '92.118.206.28'
cmd = f'git ls-remote git://{repo_ipa}/test-project.git'
sample_response = """
65860f2af612b3505ab33e4c427991f055929014        HEAD
65860f2af612b3505ab33e4c427991f055929014        refs/heads/master
1391722ced0ffadd17875b8a10e70d2e5acd6a9a        refs/tags/codeblock
3675ed1ec01147a308c142249281ee004b17ff93        refs/tags/codeblock^{}
45f03f12bb12e28e1c670442c242338d1023add3        refs/tags/testtag1
21add4ee3452eb3e433f8dfb2a23282554ad4f57        refs/tags/testtag1^{}
""".strip()

# <oid> TAB <ref> LF
# <oid>\s+HEAD should be the first line of the response unless --

"""
May be able to use <pattern> to limit results to new entries
patterns>

    When unspecified, all references, after filtering done with --heads and 
    --tags, are shown. When <patterns are specified, 
    only references matching one or more of the given patterns are displayed. 
    Each pattern is interpreted as a glob (see glob in gitglossary[7])...
"""

