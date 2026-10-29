# 来源：原项目analysis.py；发布时仅适配匿名CSV输入/输出，算法及已知局限保留。
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.cluster import KMeans
import argparse
from pathlib import Path
p = argparse.ArgumentParser(description="原分析逻辑的匿名CSV演示，不代表真实研究数据")
p.add_argument("--input", default="data/synthetic/routes.csv")
p.add_argument("--output", default="reports/generated")
args = p.parse_args()
output_dir = Path(args.output)
output_dir.mkdir(parents=True, exist_ok=True)

# ==================== 读取与预处理 ====================
df_raw = pd.read_csv(args.input)

# 清理全空行
df_raw = df_raw.dropna(how='all').reset_index(drop=True)

# 提取关键列（保留route_id用于匹配）
use_cols = [
    "route_id", "笔记发布时间", "笔记收藏数量", "笔记评论数量",
    "笔记点赞数量", "笔记转发数量", "路线节点_数量", "行类型"
]
# 动态添加节点1~节点55
node_cols = [f"节点{i}" for i in range(1, 56)]
use_cols.extend(node_cols)
df = df_raw[use_cols].copy()

# 数据类型转换
df['笔记发布时间'] = pd.to_datetime(df['笔记发布时间'], errors='coerce')
for col in ["笔记收藏数量", "笔记评论数量", "笔记点赞数量", "笔记转发数量", "路线节点_数量"]:
    df[col] = pd.to_numeric(df[col], errors='coerce')

# 删除 nodes 或 behaviors 关键信息缺失的行
df = df.dropna(subset=["行类型"])
df = df[df["行类型"].isin(["nodes", "behaviors"])].reset_index(drop=True)

print(f"有效数据行数: {len(df)}")
print("行类型分布:\n", df["行类型"].value_counts())

# ==================== 特征工程（仅 nodes） ====================
collection_time = datetime(2026, 4, 12)
df['存活天数'] = 0
df['均收藏率'] = 0.0
df['点赞增长能效'] = 0.0
df['总互动数'] = 0
df['互动强度'] = 0.0

nodes_mask = df["行类型"] == "nodes"
df.loc[nodes_mask, "存活天数"] = (collection_time - df.loc[nodes_mask, "笔记发布时间"]).dt.days
df.loc[nodes_mask, "存活天数"] = df.loc[nodes_mask, "存活天数"].clip(lower=1)  # 避免除零

df.loc[nodes_mask, "均收藏率"] = df.loc[nodes_mask, "笔记收藏数量"] / df.loc[nodes_mask, "存活天数"]
df.loc[nodes_mask, "点赞增长能效"] = df.loc[nodes_mask, "笔记点赞数量"] / df.loc[nodes_mask, "存活天数"]
df.loc[nodes_mask, "总互动数"] = (df.loc[nodes_mask, "笔记评论数量"] +
                                   df.loc[nodes_mask, "笔记点赞数量"] +
                                   df.loc[nodes_mask, "笔记转发数量"])
df.loc[nodes_mask, "互动强度"] = df.loc[nodes_mask, "总互动数"] / df.loc[nodes_mask, "笔记收藏数量"]

# ==================== KMeans 聚类 ====================
df_nodes = df[df["行类型"] == "nodes"].copy()

# 填充缺失值（关键修复）
df_nodes[['均收藏率', '点赞增长能效']] = df_nodes[['均收藏率', '点赞增长能效']].fillna(0)

X = df_nodes[["均收藏率", "点赞增长能效"]].values

# 肘部法则确定k（此处固定为4，与原逻辑一致）
k = 4
kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
df_nodes["聚类"] = kmeans.fit_predict(X)

# 将聚类标签合并回原df
df["聚类"] = -1
df.loc[df["行类型"] == "nodes", "聚类"] = df_nodes["聚类"].values

# ==================== 辅助函数：提取某行非空节点/行为列表 ====================
def extract_items(row):
    """返回该行中所有非空的节点/行为名称列表"""
    return [row[col] for col in node_cols if pd.notna(row[col])]

# ==================== 匹配 nodes 与 behaviors ====================
# 以“route_id”为键，建立映射
nodes_dict = {row["route_id"]: row for _, row in df[df["行类型"] == "nodes"].iterrows()}
behaviors_dict = {row["route_id"]: row for _, row in df[df["行类型"] == "behaviors"].iterrows()}

# 仅保留同时存在 nodes 和 behaviors 的笔记
common_links = set(nodes_dict.keys()) & set(behaviors_dict.keys())
print(f"\n可匹配的笔记数量: {len(common_links)}")

# 构建匹配后的列表（用于后续对应关系分析）
matched_pairs = []
for link in common_links:
    node_row = nodes_dict[link]
    behav_row = behaviors_dict[link]
    matched_pairs.append({
        "route_id": link,
        "聚类": node_row["聚类"],
        "节点列表": extract_items(node_row),
        "行为列表": extract_items(behav_row)
    })

# ==================== 汇总结果输出到 Excel ====================
if True:
    
    # Sheet1: 每条 nodes 的聚类分配及核心指标
    sheet1 = df_nodes[["route_id", "笔记发布时间", "笔记收藏数量", "笔记点赞数量",
                       "存活天数", "均收藏率", "点赞增长能效", "互动强度", "聚类"]].copy()
    sheet1.to_csv(output_dir / "聚类分配与指标.csv", index=False)
    
    # Sheet2: 各聚类统计特征
    cluster_stats = []
    for c in range(k):
        sub = df_nodes[df_nodes["聚类"] == c]
        if len(sub) == 0:
            continue
        cluster_stats.append({
            "聚类": c,
            "数量": len(sub),
            "均收藏率均值": sub["均收藏率"].mean(),
            "点赞增长能效均值": sub["点赞增长能效"].mean(),
            "互动强度均值": sub["互动强度"].mean(),
            "收藏数均值": sub["笔记收藏数量"].mean(),
            "评论数均值": sub["笔记评论数量"].mean(),
            "点赞数均值": sub["笔记点赞数量"].mean(),
            "转发数均值": sub["笔记转发数量"].mean()
        })
    pd.DataFrame(cluster_stats).to_csv(output_dir / "聚类统计特征.csv", index=False)
    
    # Sheet3: 各聚类中节点类型分布（前15高频）
    node_dist = []
    for c in range(k):
        nodes_in_cluster = [node for pair in matched_pairs if pair["聚类"] == c for node in pair["节点列表"]]
        if not nodes_in_cluster:
            continue
        counts = pd.Series(nodes_in_cluster).value_counts().head(15)
        for node, cnt in counts.items():
            node_dist.append({"聚类": c, "节点名称": node, "出现次数": cnt, "占比(%)": cnt/len(nodes_in_cluster)*100})
    pd.DataFrame(node_dist).to_csv(output_dir / "节点类型分布.csv", index=False)
    
    # Sheet4: 各聚类中行为类型分布（前15高频）
    behav_dist = []
    for c in range(k):
        behav_in_cluster = [behav for pair in matched_pairs if pair["聚类"] == c for behav in pair["行为列表"]]
        if not behav_in_cluster:
            continue
        counts = pd.Series(behav_in_cluster).value_counts().head(15)
        for behav, cnt in counts.items():
            behav_dist.append({"聚类": c, "行为编码": behav, "出现次数": cnt, "占比(%)": cnt/len(behav_in_cluster)*100})
    pd.DataFrame(behav_dist).to_csv(output_dir / "行为类型分布.csv", index=False)
    
    # Sheet5: 节点 → 行为 对应关系（每个聚类前10组）
    node2behav_rows = []
    for c in range(k):
        # 收集该聚类所有 (节点, 行为) 对
        pairs = []
        for pair in matched_pairs:
            if pair["聚类"] != c:
                continue
            for node in pair["节点列表"]:
                for behav in pair["行为列表"]:
                    pairs.append((node, behav))
        if not pairs:
            continue
        df_pairs = pd.DataFrame(pairs, columns=["节点", "行为"])
        # 统计每种节点对应的最常见行为
        for node, group in df_pairs.groupby("节点"):
            top_behav = group["行为"].value_counts().head(10)
            for behav, cnt in top_behav.items():
                node2behav_rows.append({
                    "聚类": c,
                    "节点名称": node,
                    "行为编码": behav,
                    "共现次数": cnt
                })
    pd.DataFrame(node2behav_rows).to_csv(output_dir / "节点_行为对应.csv", index=False)
    
    # Sheet6: 行为 → 节点 对应关系（每个聚类前10组）
    behav2node_rows = []
    for c in range(k):
        pairs = []
        for pair in matched_pairs:
            if pair["聚类"] != c:
                continue
            for behav in pair["行为列表"]:
                for node in pair["节点列表"]:
                    pairs.append((behav, node))
        if not pairs:
            continue
        df_pairs = pd.DataFrame(pairs, columns=["行为", "节点"])
        for behav, group in df_pairs.groupby("行为"):
            top_node = group["节点"].value_counts().head(10)
            for node, cnt in top_node.items():
                behav2node_rows.append({
                    "聚类": c,
                    "行为编码": behav,
                    "节点名称": node,
                    "共现次数": cnt
                })
    pd.DataFrame(behav2node_rows).to_csv(output_dir / "行为_节点对应.csv", index=False)

print(f"\n分析完成！结果已保存至：{output_dir}")