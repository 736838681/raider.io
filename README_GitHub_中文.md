# Raider.IO 同职业坦克＋DPS防具对比：GitHub Actions版

本项目仅调用 Raider.IO 公开 `/api/v1` 接口，不使用网页批量爬取。
无第三方 Python 依赖，无需 Raider.IO API Key（公开接口有限速）。

## 在 GitHub 上运行（不需要自己电脑安装 Python）

1. 在 github.com 登录，创建一个新的仓库（例如 `rio-armor-compare`）。
2. **解压压缩包**（不要直接把 ZIP 当作程序上传）。
3. 将 `raiderio_armor_compare.py`、`test_offline.py`、`玩家名单模板.csv` 上传到仓库根目录。
4. 确保仓库中存在 `.github/workflows/raiderio-armor.yml`：
   - 可以使用 Git 将整个解压目录上传；
   - 如果通过 GitHub 网页上传文件不方便保留 `.github` 文件夹，选 **Add file → Create new file**，文件名填写 `.github/workflows/raiderio-armor.yml`，将压缩包中对应 YAML 内容粘贴进去并提交。
5. 点击仓库 **Actions** → 左侧 **Raider.IO armor comparison** → **Run workflow** → **Run workflow**。
6. 先保持默认参数（5 个区域包括国服，`pages=2` 测试 API 是否可用）。确认有有效样本后，再提高 `pages`（例如 8、20），并根据需要增加 `per_spec`。
7. 运行结束后，点进那次 Workflow 执行记录；页面下方 **Artifacts** 下载 `raiderio-armor-results`。
8. 解压结果压缩包后，把 00、01、02、04、05 这几个结果文件发给 ChatGPT；如需复核逐人防具，也一并发 03。

## 参数含义

- `season`：赛季标识，默认 `season-mn-2`。
- `regions`：采集地区，默认 `us,eu,kr,tw,cn`，**包含国服**。
- `pages`：每个地区采集多少页高层 *runs*，默认 2 页只是连通性及少量样本测试；扩大覆盖请调高。
- `per_spec`：每个专精最多抓取多少个角色的当前装备。
- `min_samples`：每个坦克+DPS 组合两边各要多少个有效样本才参与正式排序。

## 结果文件

- `00_先读我_统计说明.txt`：请求数量、国服数量和局限说明。
- `01_重合件数排序.csv`：10 种同职业坦克/DPS 组合，每组最多 9 件相同装备。
- `02_九个部位逐件核对.csv`：哪个部位使用的主流物品 ID 相同、每件的出现人数。
- `03_全部玩家装备明细.csv`：每位选手当前 9 件防具的装备明细。
- `04_接口失败和排除原因.csv`：失败原因与排除记录。
- `05_专精及国服覆盖.csv`：各专精成功采样数量，含国服数量。

## 注意

- **未经过线上 API 真实运行验证。** 已有离线单元测试通过。如果 GitHub Action 日志出现 HTTP 400 / 403 / 429、字段不兼容或样本不足，需要根据该次日志调整程序，不能把空表当成有效结果。
- `runs` 的高层队伍成员不等于严格意义的 **世界各专精排行榜前 N 名**。如需严格世界专精榜，需另行提供榜单角色名单。程序支持 `--roster-file`，但当前 Github 工作流默认只运行 `runs` 自动采集模式。
- 玩家 `gear` 为读取时的当前装备快照，不保证与其高层通关时一致；不同专精装备可能随时更换。
- 比较的是每个专精样本中**各部位最常见的物品 ID**，不是完整装备集合能否在同一个角色上同时使用，不能直接视为性能损失。
- 只比较头、肩、胸、背、腕、手、腰、腿、脚；不比较项链、戒指、武器、饰品。
- 若没有有效样本或国服成功样本为零，输出会明示，不会假定已经覆盖国服。

官方说明： https://raider.io/api
