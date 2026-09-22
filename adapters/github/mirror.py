#!/usr/bin/env python3
"""自动上传 GitHub：把本仓镜像到 GitHub 仓库（分支 + 标签 + Release）。

## 为什么要有它

本仓（CNB）是开发主仓，GitHub 侧要有一份**可直接克隆**的公开副本（发布/分发用）。
手工同步的问题不是"麻烦"，是**没人知道上一次同步到哪个提交**：漏同步、同步一半、
把未发布的分支推上去，都只能靠人记。所以这里把它做成一条可复跑的流水线步骤：

* **单一真值 = git 本身**。不做本地"已同步到哪个 sha"的台账（台账一定会漂）。
  每次运行先查 GitHub 侧 ref 的实际 sha，与本地比 —— 相同即跳过（幂等，可反复跑）。
* **只镜像白名单 ref**：默认分支 + 明确的镜像分支（默认空） + 与本地一致的 Tags。
  GitHub 侧**多出来的分支不删**（删除是破坏性动作，不做）。
* **密钥只从密钥仓库来**：`imports` 把 ``GITHUB_USER`` / ``GITHUB_TOKEN`` 注入环境变量，
  本工具不读任何本地文件、不打印 token（输出处 ``_mask`` 兜底）。
* **没配密钥不是失败**：本地/PR 上常常拿不到密钥，此时打印 ``SKIPPED`` 并 exit 0
  —— 判据是"配了就同步"，不是"必须配"。

## 命令

    python -m adapters.github.mirror --check             # 只看会做什么（只读 GitHub API）
    python -m adapters.github.mirror --to-slug a/b       # 同步到 a/b（默认取 GITHUB_REPO / GITHUB_USER/LeggedStudio）
    python -m adapters.github.mirror --skip-tags         # 只同步分支
    python -m adapters.github.mirror --allow-empty       # 允许推空仓库（默认拒，见下）

## 边界（如实声明）

* **需要 CLI 凭据**（配在 ``.cnb.yml`` 的 ``imports``，仅 ``push`` / ``tag_push`` 事件）；
  没有凭据时同步**不执行**，流水线仍是绿的（``SKIPPED``）。
* 只覆盖 **git 层**（commit / branch / tag / Release 说明）。GitHub 侧的仓库设置、
  Actions、Issues、LFS 大文件**不在范围内**。
* 空仓库会被**拒绝**（``--allow-empty`` 才放行）：`git push` 对空仓库会把远端默认分支
  设成第一个被推的分支，镜像一个空仓库只会得到 GitHub 上一个 404 的仓库。
* 输出里不会打印 token；`GITHUB_TOKEN` 只经 ``http.extraheader`` 传给 git，不落在
  ``.git/config`` 或命令行参数里（后者会被 `ps` 看到）。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GITHUB_API = "https://api.github.com"
DEFAULT_REPO_NAME = "LeggedStudio"

#: 镜像分支白名单。默认只有仓库默认分支 —— 见模块文档「只镜像白名单 ref」。
DEFAULT_MIRROR_BRANCHES = ("main",)

#: 密钥仓库文件（``.cnb.yml`` 的 imports 引用同一份；此处只用于**报错时说明去哪配**）
SECRETS_URL = "https://cnb.cool/zeitvex/github-secrets/-/blob/main/github-secrets.yaml"

_PLACEHOLDER = re.compile(r"^(your-github|ghp_x|xxx|<|\$\{)")


class MirrorError(RuntimeError):
    """镜像过程中的可预期失败（凭据缺失/远端拒绝/仓库空）—— 带可执行的修法。"""


# ---------------------------------------------------------------------------
# 凭据（只从环境变量来：由 .cnb.yml 的 imports 注入）
# ---------------------------------------------------------------------------
class GithubCredentials:
    """GitHub 凭据。``user`` 可缺省（从 token 反查），``token`` 必需。"""

    def __init__(self, user: str, token: str):
        self.user = user.strip()
        self.token = token.strip()

    def __repr__(self) -> str:  # 永不打印 token
        return f"GithubCredentials(user={self.user!r}, token=***)"

    @property
    def authorization(self) -> str:
        return "Basic " + base64.b64encode(f"{self.user or 'x-access-token'}:{self.token}".encode("utf-8")).decode("ascii")


def load_credentials(env: dict | None = None) -> GithubCredentials:
    """从环境变量读凭据。**缺失即抛** —— 静默降级成"同步成功"是这里最贵的错。

    占位值（模板里的 ``your-github-username`` / ``ghp_xxxx``）与缺失同判：密钥仓库里
    忘改占位值是必然会发生的，那时**必须**报错而不是拿它去登录。
    """
    source = os.environ if env is None else env
    user = (source.get("GITHUB_USER") or "").strip()
    token = (source.get("GITHUB_TOKEN") or "").strip()
    missing = [name for name, value in (("GITHUB_USER", user), ("GITHUB_TOKEN", token)) if not value]
    if missing:
        raise MirrorError(
            f"缺少 {'/'.join(missing)} —— 检查 {SECRETS_URL} 是否已填，"
            "以及触发事件的 pipeline 是否声明了 imports（密钥仅对 push / tag_push 等事件生效）"
        )
    if _PLACEHOLDER.match(token) or _PLACEHOLDER.match(user):
        raise MirrorError(
            f"GITHUB_USER/GITHUB_TOKEN 仍是模板占位值 —— 请把 {SECRETS_URL} 改成真值"
        )
    return GithubCredentials(user=user, token=token)


def _mask(text: str, *secrets: str) -> str:
    """把 secret 从输出里抹掉（GitHub 会自动抹，本地日志不会）。"""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


# ---------------------------------------------------------------------------
# Git / HTTP 底座（薄封装，便于测试注入）
# ---------------------------------------------------------------------------
def run_git(args, cwd: str = ROOT, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env,
    )


def _git(*args: str, cwd: str = ROOT, check: bool = True) -> str:
    completed = run_git(list(args), cwd=cwd)
    if check and completed.returncode != 0:
        raise MirrorError(f"git {' '.join(args)} 失败：{(completed.stderr or completed.stdout).strip()}")
    return (completed.stdout or "").strip()


def git_push_env(token: str, user: str, base_env: dict | None = None) -> dict:
    """把凭据经 ``http.extraheader`` 传给 git：**不进 .git/config、不进 argv**。

    为什么不用 ``https://user:token@host``：那条 URL 会落进 ``.git/config`` 的 remote
    与 ``FETCH_HEAD``/reflog，事后清理容易漏；argv 形态又会被同机 ``ps`` 看到。
    """
    env = dict(os.environ if base_env is None else base_env)
    authorization = "Basic " + base64.b64encode(f"{user or 'x-access-token'}:{token}".encode("utf-8")).decode("ascii")
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "http.extraheader"
    env["GIT_CONFIG_VALUE_0"] = f"Authorization: {authorization}"
    return env


def api(url: str, creds: GithubCredentials, method: str = "GET", payload: dict | None = None):
    """调 GitHub REST。404 返回 ``None``（"不存在"是正常分支，不是异常）。"""
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", creds.authorization)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("User-Agent", "legged-studio-github-mirror")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        detail = _mask(error.read().decode("utf-8", errors="replace").strip(), creds.token)
        raise MirrorError(f"GitHub API {method} {url} -> {error.code}：{detail[:300]}") from None
    except urllib.error.URLError as error:
        raise MirrorError(f"连不上 GitHub（{error.reason}）—— 检查出网/代理") from None


# ---------------------------------------------------------------------------
# 收集本地状态
# ---------------------------------------------------------------------------
def local_branches(names: list[str]) -> dict:
    """``{分支名: sha}``；本地不存在的分支直接跳过（白名单里写了但仓里没有）。"""
    found = {}
    for name in names:
        completed = run_git(["rev-parse", "--verify", f"refs/heads/{name}"])
        if completed.returncode == 0:
            found[name] = completed.stdout.strip()
    return found


def local_tags() -> dict:
    """``{tag: sha}`` —— 按 peeled^{} 取**提交 sha**（annotated tag 也要能对上 GitHub 侧）。"""
    listing = _git("for-each-ref", "--format=%(refname:short) %(objectname) %(*objectname)", "refs/tags")
    tags = {}
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        name, object_sha = parts[0], parts[1]
        tags[name] = parts[2] if len(parts) > 2 else object_sha
    return tags


def head_commit() -> str:
    return _git("rev-parse", "HEAD")


def commit_subject(sha: str) -> str:
    return _git("log", "-1", "--format=%s", sha)


def branch_sha_from_github(creds: GithubCredentials, slug: str, branch: str) -> str | None:
    return ((api(f"{GITHUB_API}/repos/{slug}/branches/{urllib.parse.quote(branch)}", creds) or {})
            .get("commit") or {}).get("sha")


def tag_sha_from_github(creds: GithubCredentials, slug: str, tag: str) -> str | None:
    node = api(f"{GITHUB_API}/repos/{slug}/git/ref/tags/{urllib.parse.quote(tag)}", creds)
    if not node:
        return None
    sha = (node.get("object") or {}).get("sha")
    if (node.get("object") or {}).get("type") == "tag":
        annotated = api(f"{GITHUB_API}/repos/{slug}/git/tags/{sha}", creds) or {}
        sha = (annotated.get("object") or {}).get("sha") or sha
    return sha


# ---------------------------------------------------------------------------
# 计划（**先算后做**：--check 与真跑走同一份计划，避免"看的和做的不是一件事"）
# ---------------------------------------------------------------------------
def build_plan(creds: GithubCredentials, slug: str, branches: dict, tags: dict,
               with_tags: bool = True) -> dict:
    """算出缺哪些 ref。返回 ``{"actions": [...], "remote_branches": n, "remote_tags": n}``。

    判据一律是 **sha 相等**（不是"名字存在"）：名字在但指向老提交，正是要修的那种漂移。
    """
    repo = api(f"{GITHUB_API}/repos/{slug}", creds)
    actions: list[dict] = []
    if repo is None:
        actions.append({"kind": "create_repo", "slug": slug})
    else:
        if not repo.get("permissions", {}).get("push", True):
            raise MirrorError(f"{slug} 已存在但当前 token 没有 push 权限 —— 换一个有 repo 权限的 PAT")

    for name, sha in sorted(branches.items()):
        remote = branch_sha_from_github(creds, slug, name) if repo is not None else None
        if remote != sha:
            actions.append({"kind": "branch",
                            "reason": "远端缺失" if remote is None else "远端指向其它提交",
                            "branch": name, "sha": sha, "remote": remote})

    if with_tags:
        for name, sha in sorted(tags.items()):
            remote = tag_sha_from_github(creds, slug, name) if repo is not None else None
            if remote != sha:
                actions.append({"kind": "tag", "tag": name, "sha": sha, "remote": remote})

    return {"actions": actions, "created": repo is None}


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------
def remote_url(slug: str) -> str:
    return f"https://github.com/{slug}.git"


def mirror(creds: GithubCredentials, slug: str, branches: dict, tags: dict,
           with_tags: bool = True, allow_empty: bool = False, dry_run: bool = False,
           log=print) -> dict:
    """把本地 ref 推到 GitHub。返回 ``{"pushed": [...], "skipped": bool}``。

    顺序有意如此：**先推分支**（建立默认分支，仓库才不是空的），再推 tag，最后建 Release。
    """
    head = head_commit()
    if not allow_empty:
        completed = run_git(["rev-list", "--count", "HEAD"])
        count = int(completed.stdout.strip() or "0") if completed.returncode == 0 else 0
        if count == 0:
            raise MirrorError(
                "本地 HEAD 没有任何提交 —— 拒绝对空仓库做镜像"
                "（否则 GitHub 上会得到一个默认分支指向 404 的空仓）；确实要这么做时加 --allow-empty"
            )

    plan = build_plan(creds, slug, branches, tags, with_tags=with_tags)
    log(f"  本地 HEAD      {head[:8]}  {commit_subject(head)}")
    log(f"  目标仓库       {slug}")
    log(f"  待同步         {len(plan['actions'])} 项"
        f"{'（仓库将被创建）' if plan['created'] else ''}")
    for action in plan["actions"]:
        if action["kind"] == "branch":
            log(f"    branch {action['branch']}  {action['sha'][:8]}（{action['reason']}）")
        elif action["kind"] == "tag":
            log(f"    tag    {action['tag']}  {action['sha'][:8]}")
    if not plan["actions"]:
        log("  已是最新：GitHub 侧与本地逐 sha 一致，无需推送")
        return {"pushed": [], "skipped": True, "plan": plan}
    if dry_run:
        log("  --check：只报告，不推送")
        return {"pushed": [], "skipped": False, "plan": plan, "dry_run": True}

    push_env = git_push_env(creds.token, creds.user)
    url = remote_url(slug)

    if plan["created"]:
        created = api(f"{GITHUB_API}/user/repos", creds, method="POST", payload={
            "name": slug.split("/")[-1], "private": False,
            "description": "Legged Studio —— 腿足机器人强化学习工作室（CNB 主仓的镜像）",
        })
        if created is None:
            raise MirrorError(f"创建 GitHub 仓库 {slug} 失败（API 返回 404/空）")

    pushed: list[str] = []
    for action in plan["actions"]:
        if action["kind"] != "branch":
            continue
        ref = f"refs/heads/{action['branch']}"
        completed = run_git(["push", url, f"{ref}:{ref}"], env=push_env)
        if completed.returncode != 0:
            raise MirrorError(
                _mask(f"推送分支 {action['branch']} 失败："
                      f"{(completed.stderr or completed.stdout).strip()}", creds.token)
            )
        pushed.append(f"branch:{action['branch']}")
        log(f"  ✓ branch {action['branch']} -> {action['sha'][:8]}")

    tag_actions = [a for a in plan["actions"] if a["kind"] == "tag"]
    if tag_actions:
        # 一次性推全部 tag：逐个推会重复建连，而 tag 数量会随版本累积。
        refs = [f"refs/tags/{a['tag']}:refs/tags/{a['tag']}" for a in tag_actions]
        completed = run_git(["push", url, *refs], env=push_env)
        if completed.returncode != 0:
            raise MirrorError(
                _mask(f"推送 tag 失败：{(completed.stderr or completed.stdout).strip()}", creds.token)
            )
        for action in tag_actions:
            pushed.append(f"tag:{action['tag']}")
            log(f"  ✓ tag    {action['tag']}")

    return {"pushed": pushed, "skipped": False, "plan": plan, "head": head}


def ensure_release(creds: GithubCredentials, slug: str, tag: str, log=print) -> bool:
    """给 tag 建 GitHub Release（已存在则跳过）。

    与 ``git:release`` 的分工：那个建在**本仓（CNB）**，这个建在 **GitHub 镜像**上。
    两边都建，是因为两边都有人直接下载 —— 只有本仓有 Release 时，GitHub 访客看不到版本。
    """
    existing = api(f"{GITHUB_API}/repos/{slug}/releases/tags/{urllib.parse.quote(tag)}", creds)
    if existing:
        log(f"  · Release {tag} 已存在，跳过")
        return False
    subject = commit_subject(_git("rev-parse", f"refs/tags/{tag}^{{commit}}"))
    body = "\n".join([
        f"Legged Studio `{tag}`",
        "",
        f"- 提交：`{_git('rev-parse', f'refs/tags/{tag}^{{commit}}')}`",
        f"- 说明：{subject}",
        f"- 本仓（CNB）主仓：https://cnb.cool/zeitvex/LeggedStudio",
        "",
        "本 Release 由 CNB 流水线自动同步（`adapters/github/mirror.py`）生成。",
    ])
    created = api(f"{GITHUB_API}/repos/{slug}/releases", creds, method="POST", payload={
        "tag_name": tag, "name": tag, "body": body, "draft": False, "prerelease": False,
    })
    if created is None:
        raise MirrorError(f"创建 Release {tag} 失败")
    log(f"  ✓ Release {tag}")
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def resolve_slug(creds: GithubCredentials | None, explicit: str | None) -> str:
    if explicit:
        return explicit.strip().strip("/")
    env_slug = (os.environ.get("GITHUB_REPO") or "").strip().strip("/")
    if env_slug:
        return env_slug
    user = (creds.user if creds else "") or (os.environ.get("GITHUB_USER") or "").strip()
    if not user:
        raise MirrorError("无法确定目标仓库：给 --to-slug，或在密钥里填 GITHUB_USER / GITHUB_REPO")
    return f"{user}/{DEFAULT_REPO_NAME}"


def mirror_branches() -> list[str]:
    raw = (os.environ.get("GITHUB_MIRROR_BRANCHES") or "").strip()
    names = [item.strip() for item in raw.split(",") if item.strip()] or list(DEFAULT_MIRROR_BRANCHES)
    return names


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="把本仓镜像到 GitHub（分支 / 标签 / Release）",
    )
    parser.add_argument("--to-slug", help="目标 GitHub 仓库，形如 user/repo（默认 GITHUB_REPO 或 GITHUB_USER/LeggedStudio）")
    parser.add_argument("--check", action="store_true", help="只报告会同步什么，不做任何写操作")
    parser.add_argument("--skip-tags", action="store_true", help="只同步分支，不推 tag、不建 Release")
    parser.add_argument("--allow-empty", action="store_true", help="允许对没有提交的仓库做镜像（默认拒绝）")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    print("== 自动上传 GitHub（镜像） ==")
    try:
        creds = load_credentials()
    except MirrorError as error:
        # 没配密钥**不是失败**：本地 / PR / fork 上本来就拿不到（imports 只对 push/tag_push 生效）。
        print(f"SKIPPED: {error}")
        print("本步不判红 —— 配好密钥后由 push / tag_push 事件自动执行。")
        return 0
    try:
        slug = resolve_slug(creds, args.to_slug)
        branches = local_branches(mirror_branches())
        if not branches:
            raise MirrorError(
                f"本地没有镜像白名单里的分支（{[*mirror_branches()]}）—— "
                "检查 GITHUB_MIRROR_BRANCHES 或当前检出的是不是浅克隆"
            )
        tags = {} if args.skip_tags else local_tags()
        with_tags = not args.skip_tags
        result = mirror(creds, slug, branches, tags, with_tags=with_tags,
                        allow_empty=args.allow_empty, dry_run=args.check)
        if with_tags and not args.check:
            for action in result.get("plan", {}).get("actions", []):
                if action["kind"] == "tag":
                    ensure_release(creds, slug, action["tag"])
        if args.check:
            print(f"CHECK: 计划同步 {len(result['plan']['actions'])} 项（未推送）")
        elif result["skipped"]:
            print("OK: 已是最新，无需推送")
        else:
            print(f"OK: 同步完成 {len(result['pushed'])} 项 -> https://github.com/{slug}")
    except MirrorError as error:
        print(f"FAIL: {_mask(str(error), os.environ.get('GITHUB_TOKEN') or '')}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
