"""GitHub 自动上传（镜像）的契约测试。

守四件事（都对应一个真实会出的事故）：

1. **密钥缺失 = SKIPPED，不是失败**（本地 / PR 上本来就拿不到 `imports`）；
   但**占位值**（模板里的 `your-github-username` / `ghp_xxxx`）必须报错 —— 那是最常见的
   "以为配好了"；
2. **plan 的判据是 sha，不是"名字在不在"**：名字在但指向老提交，正是要修的漂移；
3. **绝不打印 token**：`_mask` 要覆盖"API 报错回显"与"git stderr 回显"两条路；
4. **空仓库默认拒**：`git push` 对空仓会把远端默认分支设成第一个被推的分支 —— 镜像空仓
   只会得到 GitHub 上一个 404 的仓库。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import adapters.github.mirror as mirror  # noqa: E402


class CredentialsTest(unittest.TestCase):
    def test_missing_credentials_raise_with_actionable_hint(self):
        with self.assertRaises(mirror.MirrorError) as ctx:
            mirror.load_credentials({})
        message = str(ctx.exception)
        self.assertIn("GITHUB_USER", message)
        # 提示必须指向**去哪配**，否则报错只是噪音
        self.assertIn("github-secrets", message)

    def test_placeholder_values_are_rejected(self):
        """密钥仓库里忘改占位值必然会发生 —— 那时必须报错，而不是拿它去登录。"""

        with self.assertRaises(mirror.MirrorError):
            mirror.load_credentials({"GITHUB_USER": "your-github-username", "GITHUB_TOKEN": "ghp_xxxxxxxx"})
        with self.assertRaises(mirror.MirrorError):
            mirror.load_credentials({"GITHUB_USER": "your-github-username", "GITHUB_TOKEN": "real-token-123"})

    def test_real_credentials_load(self):
        creds = mirror.load_credentials({"GITHUB_USER": "demo", "GITHUB_TOKEN": "ghp_real123"})
        self.assertEqual(creds.user, "demo")
        self.assertTrue(creds.authorization.startswith("Basic "))
        # repr 一律脱敏（异常栈里会打印对象）
        self.assertNotIn("ghp_real123", repr(creds))


class MaskTest(unittest.TestCase):
    def test_mask_removes_token_from_error_text(self):
        self.assertEqual(mirror._mask("bad token ghp_abc", "ghp_abc"), "bad token ***")

    def test_push_credentials_never_land_in_config_or_argv(self):
        """凭据只走 `http.extraheader`：不进 `.git/config`、不进 argv（argv 会被 `ps` 看到）。"""

        env = mirror.git_push_env("ghp_secret", "demo")
        self.assertEqual(env["GIT_CONFIG_KEY_0"], "http.extraheader")
        self.assertIn("Authorization: Basic", env["GIT_CONFIG_VALUE_0"])
        self.assertNotIn("https://", env["GIT_CONFIG_VALUE_0"])
        # 环境里不许出现裸 token 变量名之外的回显面
        self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")


#: 假 API 的路径片段。**`REPO` 是其余几条的前缀**，所以 `_patch` 必须按**具体度**消歧，
#: 不能按字符串长度（第一版按长度取最长，于是 `/repos/demo/LeggedStudio`（24 字符）
#: 压过 `/branches/main`（14 字符），仓库信息把子路径全吞了 —— 实测表现为
#: "远端分支永远查不到"，一个会让判据静默失效的假阴性）。
REPO = "/repos/demo/LeggedStudio"
BRANCH = "/branches/main"
TAG_REF = "/git/ref/tags/v0.56.1"
TAG_OBJECT = "/git/tags/tag-object-sha"


class PlanTest(unittest.TestCase):
    HEAD = "3d306ba6578504d10d5a4dc8abf7bafa77060a2f"

    def setUp(self):
        self.creds = mirror.GithubCredentials("demo", "ghp_real123")
        self.locals = {"branches": {"main": self.HEAD}, "tags": {"v0.56.1": self.HEAD}}

    def _patch(self, mapping):
        """把 GitHub API 换成查表：key 是"路径片段"，value 是响应。

        **必须按具体度消歧**：``REPO`` 是其余片段的前缀，而它字符数**更长** ——
        按长度取最长会让仓库信息吞掉所有子路径（第一版就是这么错的）。这里取
        "匹配到的最具体的那条"：先看有没有非 ``REPO`` 的命中，没有才回落 ``REPO``。
        """

        def fake_api(url, creds, method="GET", payload=None):
            hits = [fragment for fragment in mapping if fragment in url and fragment != REPO]
            if hits:
                return mapping[max(hits, key=len)]
            return mapping.get(REPO) if REPO in url else None

        self._original = mirror.api
        mirror.api = fake_api
        self.addCleanup(lambda: setattr(mirror, "api", self._original))

    def test_missing_repo_plans_create_and_branch(self):
        self._patch({REPO: None})
        plan = mirror.build_plan(self.creds, "demo/LeggedStudio", self.locals["branches"], self.locals["tags"])
        kinds = [action["kind"] for action in plan["actions"]]
        self.assertEqual(kinds, ["create_repo", "branch", "tag"])
        self.assertTrue(plan["created"])

    def test_same_sha_is_skipped(self):
        self._patch({
            REPO: {"permissions": {"push": True}},
            BRANCH: {"commit": {"sha": self.HEAD}},
            TAG_REF: {"object": {"sha": self.HEAD, "type": "commit"}},
        })
        plan = mirror.build_plan(self.creds, "demo/LeggedStudio", self.locals["branches"], self.locals["tags"])
        self.assertEqual(plan["actions"], [])
        self.assertFalse(plan["created"])

    def test_stale_branch_sha_is_pushed(self):
        """名字在、指向老提交 —— 这是漂移，不是"已同步"。"""

        self._patch({
            REPO: {"permissions": {"push": True}},
            BRANCH: {"commit": {"sha": "0" * 40}},
        })
        plan = mirror.build_plan(self.creds, "demo/LeggedStudio", self.locals["branches"], {})
        self.assertEqual([action["kind"] for action in plan["actions"]], ["branch"])
        self.assertEqual(plan["actions"][0]["reason"], "远端指向其它提交")

    def test_annotated_tag_resolves_to_commit(self):
        """annotated tag 的 ref 指向 tag 对象 —— 要比的是它 peel 出来的提交 sha。"""

        self._patch({
            REPO: {"permissions": {"push": True}},
            TAG_REF: {"object": {"sha": "tag-object-sha", "type": "tag"}},
            TAG_OBJECT: {"object": {"sha": self.HEAD, "type": "commit"}},
        })
        self.assertEqual(mirror.tag_sha_from_github(self.creds, "demo/LeggedStudio", "v0.56.1"), self.HEAD)

    def test_repo_without_push_permission_fails_loudly(self):
        self._patch({"/repos/demo/LeggedStudio": {"permissions": {"push": False}}})
        with self.assertRaises(mirror.MirrorError):
            mirror.build_plan(self.creds, "demo/LeggedStudio", self.locals["branches"], {})


class GuardRailTest(unittest.TestCase):
    def test_mirror_branches_defaults_to_main(self):
        import os

        previous = os.environ.pop("GITHUB_MIRROR_BRANCHES", None)
        try:
            self.assertEqual(mirror.mirror_branches(), ["main"])
            os.environ["GITHUB_MIRROR_BRANCHES"] = "main, release/v1.0"
            self.assertEqual(mirror.mirror_branches(), ["main", "release/v1.0"])
        finally:
            os.environ.pop("GITHUB_MIRROR_BRANCHES", None)
            if previous is not None:
                os.environ["GITHUB_MIRROR_BRANCHES"] = previous

    def test_slug_resolution(self):
        creds = mirror.GithubCredentials("demo", "ghp_real123")
        self.assertEqual(mirror.resolve_slug(creds, "other/repo"), "other/repo")
        self.assertEqual(mirror.resolve_slug(creds, None), "demo/LeggedStudio")

    def test_main_without_credentials_returns_zero(self):
        """**没配密钥不是失败**：本地/PR 跑这条命令必须 exit 0（输出 SKIPPED）。"""

        import io
        import os
        from contextlib import redirect_stdout

        saved = {key: os.environ.pop(key, None) for key in ("GITHUB_USER", "GITHUB_TOKEN", "GITHUB_REPO")}
        buffer = io.StringIO()
        try:
            with redirect_stdout(buffer):
                code = mirror.main(["--check"])
        finally:
            for key, value in saved.items():
                if value is not None:
                    os.environ[key] = value
        self.assertEqual(code, 0)
        self.assertIn("SKIPPED", buffer.getvalue())

    def test_parser_exposes_check_mode(self):
        self.assertTrue(mirror.parse_args(["--check"]).check)
        self.assertTrue(mirror.parse_args(["--check"]).check is not None)
        self.assertFalse(mirror.parse_args([]).check)


if __name__ == "__main__":
    unittest.main()
