
primary_refs = \
"""
65860f2af612b3505ab33e4c427991f055929014        HEAD
65860f2af612b3505ab33e4c427991f055929014        refs/heads/master
abc60f2af612b3505ab33e4c427991f055929014        refs/heads/dev
1391722ced0ffadd17875b8a10e70d2e5acd6a9a        refs/tags/codeblock
3675ed1ec01147a308c142249281ee004b17ff93        refs/tags/codeblock^{}
45f03f12bb12e28e1c670442c242338d1023add3        refs/tags/testtag1
21add4ee3452eb3e433f8dfb2a23282554ad4f57        refs/tags/testtag1^{}
"""

good_mirror_refs = \
"""
65860f2af612b3505ab33e4c427991f055929014        HEAD
65860f2af612b3505ab33e4c427991f055929014        refs/heads/master
abc60f2af612b3505ab33e4c427991f055929014        refs/heads/dev
1391722ced0ffadd17875b8a10e70d2e5acd6a9a        refs/tags/codeblock
3675ed1ec01147a308c142249281ee004b17ff93        refs/tags/codeblock^{}
45f03f12bb12e28e1c670442c242338d1023add3        refs/tags/testtag1
21add4ee3452eb3e433f8dfb2a23282554ad4f57        refs/tags/testtag1^{}
"""

missing_tag_mirror_refs = \
"""
65860f2af612b3505ab33e4c427991f055929014        HEAD
65860f2af612b3505ab33e4c427991f055929014        refs/heads/master
abc60f2af612b3505ab33e4c427991f055929014        refs/heads/dev
1391722ced0ffadd17875b8a10e70d2e5acd6a9a        refs/tags/codeblock
3675ed1ec01147a308c142249281ee004b17ff93        refs/tags/codeblock^{}
"""

stale_commit_mirror_refs = \
"""
65860f2af612b3505ab33e4c427991f055929014        HEAD
65860f2af612b3505ab33e4c427991f055929014        refs/heads/master
abc60f2af612b3505ab33e4c427991f055921111        refs/heads/dev
1391722ced0ffadd17875b8a10e70d2e5acd6a9a        refs/tags/codeblock
3675ed1ec01147a308c142249281ee004b17ff93        refs/tags/codeblock^{}
45f03f12bb12e28e1c670442c242338d1023add3        refs/tags/testtag1
21add4ee3452eb3e433f8dfb2a23282554ad4f57        refs/tags/testtag1^{}
"""

missing_branch_mirror_refs = \
"""
65860f2af612b3505ab33e4c427991f055929014        HEAD
65860f2af612b3505ab33e4c427991f055929014        refs/heads/master
1391722ced0ffadd17875b8a10e70d2e5acd6a9a        refs/tags/codeblock
3675ed1ec01147a308c142249281ee004b17ff93        refs/tags/codeblock^{}
45f03f12bb12e28e1c670442c242338d1023add3        refs/tags/testtag1
21add4ee3452eb3e433f8dfb2a23282554ad4f57        refs/tags/testtag1^{}
"""
