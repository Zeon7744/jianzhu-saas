# CHANGELOG

> jianzhu-saas 变更日志（Keep a Changelog 结构，随 patch/feat/chore commit 补充）

## [Unreleased] — 2026-10-24

本周三端巡检自动补全（billing 收款层 / paywall 门控 / 文档 / 冒烟测试）

## 近期变更摘要

### 10-24

- `1fc8624` chore(probe): 三端同步探测探针文件（临时）
### 10-23

- `d625bf3` docs(week3): 补 3 篇 docs + 静态冒烟 smoke_static.sh
### 10-22

- `92e8328` ci: 三端全自动镜像（Gitee SSH + GitCode token）
- `04d1768` docs(readme): 先体验后付费 + 用户回馈驱动迭代
- `837c0e9` docs(readme): 统一补「面包多 Pay收款+社区发布」双区块（全仓共存）
- `3d9a30a` revert(billing): 撤 BufPay 网关，全仓统一面包多 Pay收款+社区发布

## 维护说明

- 遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/) 结构
- 格式：`commit_sha` 简述（feat/fix/chore/docs/refactor/test）
- 生成时间：2026-10-24