#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试寻路算法和地图连通性
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from app.container import build_container


class MockContext:
    def __init__(self):
        self.data_dir = "data"


def test_pathfinding():
    """测试东阿到南皮的路径查找"""
    print("=== 测试寻路算法和地图连通性 ===\n")

    # 创建模拟上下文
    context = MockContext()

    # 构建容器
    try:
        container = build_container(context)
        print("✓ 容器构建成功")
    except Exception as e:
        print(f"✗ 容器构建失败: {e}")
        return

    # 获取寻路服务
    siege_service = container.siege_service
    map_service = container.map_service

    print("✓ 获取到寻路服务")

    # 测试用例：东阿 -> 南皮
    test_cases = [
        ("东阿", "南皮"),
        ("南皮", "东阿"),
        ("洛阳", "成都"),
        ("邺", "临淄"),
        ("许昌", "彭城"),
    ]

    print("\n=== 测试路径查找 ===")
    for src, dst in test_cases:
        print(f"\n测试: {src} -> {dst}")

        # 检查城市是否存在
        src_obj = siege_service._city_obj(src)
        dst_obj = siege_service._city_obj(dst)

        if not src_obj:
            print(f"  ✗ 源城市 '{src}' 不存在")
            continue
        if not dst_obj:
            print(f"  ✗ 目标城市 '{dst}' 不存在")
            continue

        print("  ✓ 城市存在")

        # 查找路径
        path = siege_service._shortest_path(src, dst)

        if path:
            print(f"  ✓ 找到路径: {' -> '.join(path)}")
            print(f"  ✓ 路径长度: {len(path)} 个城市")
            print(f"  ✓ 路径段数: {len(path) - 1} 段")
        else:
            print("  ✗ 未找到连通路径")

            # 调试信息：显示两个城市的邻居
            src_neighbors = siege_service._neighbors(src)
            dst_neighbors = siege_service._neighbors(dst)
            print(f"  🔍 {src} 的邻居: {src_neighbors}")
            print(f"  🔍 {dst} 的邻居: {dst_neighbors}")

    print("\n=== 地图数据检查 ===")

    # 检查所有城市的lines定义是否有重复门名
    map_data = map_service.graph()
    cities = map_data.cities

    duplicate_issues = []

    for city_name, city_info in cities.items():
        lines = city_info.get("lines", {})
        if isinstance(lines, dict):
            # 检查是否有重复的门名
            door_names = list(lines.keys())
            if len(door_names) != len(set(door_names)):
                # 找到重复的门名
                from collections import Counter

                door_counts = Counter(door_names)
                duplicates = [door for door, count in door_counts.items() if count > 1]
                duplicate_issues.append(f"{city_name}: 重复门名 {duplicates}")

    if duplicate_issues:
        print("✗ 发现重复门名问题:")
        for issue in duplicate_issues:
            print(f"  - {issue}")
    else:
        print("✓ 未发现重复门名问题")

    print("\n=== 测试完成 ===")


if __name__ == "__main__":
    test_pathfinding()
