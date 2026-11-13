# 2-BigAtotal2

这是一个静态 HTML 行业研究看板，基于飞书表格中的模块设计，并使用真实行情数据生成页面输出。

## 地址

- GitHub：<https://github.com/leejiazhi88-gif/2-BigAtotal2>
- 在线页面：<https://leejiazhi88-gif.github.io/2-BigAtotal2/>

## 页面

- 主页面：`outputs/index.html`
- 申万行业行情数据：`outputs/sector_real_data.js`
- 行业成分公司与市值：`outputs/company_details_data.js`，按当前上市公司及申万 SW2021 归属展示，市值单位为亿元
- 市场估值与情绪模块数据：`outputs/market_modules_data.js`

## 图表打点与分位

当前页面的价格、隐含利润、PE、估值与交易热度曲线统一使用上交所交易日历：每周最后一个交易日取一点，当前周取快照中最新交易日。各行业与页签共享同一组实际日期；缺失日期留空，不用附近日期替代。成交额和成交量仍是打点当日的值，不是周累计。

历史分位继续使用所选区间内全部有效正日度PE/PB，含相等值，不按周样本排名。与2.2比较时，必须同时对齐区间起止日期和被评估的PE日期；周打点与季度打点本身不改变相同日度样本下的分位。

## 数据来源

- Tushare `index_classify` / `sw_daily`
- Tushare `index_member_all` / `stock_basic` / `daily_basic`：公司明细及最新可用市值
- Tushare `daily_basic` / `daily` / `margin` / `moneyflow_hsgt` / `block_trade` / `new_share`

本仓库不提交飞书读取缓存、`.env`、密钥或访问 token。

## 重新生成

```powershell
python work/build_real_sector_data.py
python work/build_market_modules_data.py
python work/build_company_data.py
```

只重建现有快照的曲线采样、保留行情截止日及原始日线版本：

```sh
python3 work/build_real_sector_data.py --reuse-snapshot
```

该模式读取快照的 `sourceSnapshotDate`（旧快照按 `generatedAt` 日期）对应的本地 `work/.tushare-cache/`；缺少原日线缓存会明确失败。常规生成命令仍获取最新可用行情，并自动按周打点。
