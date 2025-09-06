# AstrBot SLG 插件

一个为 AstrBot 设计的 SLG (策略游戏) 插件，让用户可以在聊天中体验三国题材的策略游戏。

## 功能特性

### 核心游戏机制

- **资源管理**: 管理四种基础资源——粮食、金钱、石头和军队
- **建筑系统**: 升级四种建筑——农田、钱庄、采石场和军营，以提高资源产量和容量
- **角色收集**: 通过抽卡系统收集三国武将，每个角色都有独特的技能
- **队伍编成**: 将收集到的角色编入队伍，进行战斗
- **同盟系统**: 创建或加入同盟，与其他玩家合作
- **战斗系统**: 基于角色技能和兵力进行战术战斗模拟
- **基地系统**: 拥有和迁移基地城市

### 地图系统

- **三国地图**: 基于真实三国时期地理位置的地图系统
- **城市关系**: 城市之间通过城门连接，形成战线
- **战线推进**: 可以推进城市间的战线，包含里程碑系统
- **地图可视化**: 支持将地图渲染为图片进行展示

### AI 集成

- **智能战斗**: 使用 LLM 进行战斗结果预测和战术分析
- **动态评估**: 基于角色技能和兵力进行多维度战斗评估

## 技术架构

### 设计模式

- **依赖注入**: 使用容器模式管理服务依赖
- **端口与适配器**: 通过端口抽象数据访问，支持不同存储后端
- **管道模式**: 使用处理管道处理游戏事件

### 目录结构

```
astrbot_plugin_slg/
├── app/                    # 应用层
│   ├── container.py        # 依赖注入容器
│   └── __init__.py
├── app_pipeline/           # 处理管道
│   ├── pipeline.py         # 管道实现
│   ├── stages.py           # 处理阶段
│   └── __init__.py
├── domain/                 # 领域层
│   ├── constants.py        # 游戏常量
│   ├── entities.py         # 领域实体
│   ├── ports.py            # 端口定义
│   ├── services.py         # 核心服务
│   ├── services_alliance.py # 同盟服务
│   ├── services_base.py    # 基地服务
│   ├── services_battle.py # 战斗服务
│   ├── services_gacha.py  # 抽卡服务
│   ├── services_resources.py # 资源服务
│   ├── services_team.py   # 队伍服务
│   └── __init__.py
├── infra/                 # 基础设施层
│   ├── assets.py           # 资源管理
│   ├── astr_llm.py         # LLM 集成
│   ├── character_provider.py # 角色数据提供
│   ├── hooks.py            # 钩子系统
│   ├── html_renderer.py    # HTML 渲染
│   ├── map_json_provider.py # 地图数据提供
│   ├── map_provider.py     # 地图服务提供
│   ├── sqlite_player_repo.py # 玩家数据仓库
│   ├── sqlite_repo.py      # 通用数据仓库
│   └── __init__.py
├── characters/             # 角色数据
│   └── character.json      # 角色定义
├── map/                   # 地图数据
│   └── three_kingdoms.json # 三国地图定义
├── picture/               # 图片资源
│   ├── bg.jpg
│   ├── default.png
│   └── PASS.png
├── main.py                # 插件入口
├── metadata.yaml          # 插件元数据
├── requirements.txt       # 依赖
├── _conf_schema.json      # 配置模式
└── README.md              # 说明文档
```

### 核心组件

#### 领域服务

- **ResourceService**: 管理玩家资源、建筑升级和资源结算
- **TeamService**: 处理队伍管理、角色分配和升级
- **AllianceService**: 管理同盟创建、加入和成员管理
- **BattleService**: 处理战斗模拟和结果计算
- **GachaService**: 实现抽卡系统和角色获取
- **BaseService**: 管理玩家基地和迁城功能
- **MapService**: 提供地图数据和城市关系查询
- **StateService**: 管理游戏状态，如战线进度

#### 基础设施

- **SQLitePlayerRepository**: 玩家数据的 SQLite 持久化
- **SQLiteStateRepository**: 游戏状态的 SQLite 持久化
- **AstrLLM**: 集成 AstrBot 的 LLM 提供商
- **JsonMapProvider**: 从 JSON 文件加载地图数据
- **CharacterProvider**: 加载和管理角色数据

## 游戏玩法

### 基础命令

- `/slg 加入` - 加入游戏
- `/slg 资源` - 查看资源状态
- `/slg 升级 <建筑>` - 升级指定建筑
- `/slg 抽卡 <次数>` - 进行抽卡
- `/slg 队伍` - 查看队伍配置
- `/slg 上阵 <角色> <队伍> [槽位]` - 将角色编入队伍
- `/slg 补兵 <队伍>` - 为队伍补充兵力
- `/slg 基地` - 查看当前基地
- `/slg 迁城 <城市>` - 迁移到指定城市

### 同盟命令

- `/slg 同盟创建 <名称>` - 创建同盟
- `/slg 同盟加入 <名称>` - 加入同盟
- `/slg 同盟成员 [名称]` - 查看同盟成员
- `/slg 同盟列表` - 查看所有同盟

### 战斗命令

- `/slg 进攻 <玩家ID>` - 向其他玩家发起进攻

### 地图命令

- `/slg_map` - 查看大地图
- `/line <城市>` - 查看城市战线
- `/line_push <城市> <城门> <进度>` - 推进战线进度

## 数据模型

### 玩家 (Player)

```python
@dataclass
class Player:
    user_id: str           # 用户唯一标识
    nickname: str          # 玩家昵称
    created_at: int        # 创建时间
    last_tick: int         # 上次结算时间
    grain: int            # 粮食数量
    gold: int             # 金钱数量
    stone: int            # 石头数量
    troops: int           # 军队数量
    farm_level: int       # 农田等级
    bank_level: int       # 钱庄等级
    quarry_level: int     # 采石场等级
    barracks_level: int   # 军营等级
    draw_count: int       # 累计抽卡次数
```

### 角色 (Character)

```python
@dataclass
class Character:
    name: str             # 角色名称
    title: str            # 角色称号
    background: str       # 背景故事
    skills: List[Skill]   # 技能列表
```

### 城市 (City)

```python
@dataclass
class City:
    name: str             # 城市名称
    province: str         # 所属州
    ntype: NodeType       # 节点类型 (CITY/PASS/RESOURCE)
    capital: bool         # 是否为州府
```

## 配置和部署

### 依赖要求

本插件目前没有外部依赖，所有功能均基于 Python 标准库和 AstrBot 框架实现。

### 安装步骤

1. 将插件目录放置到 AstrBot 的插件目录中
2. 确保 AstrBot 正确加载插件
3. 插件会自动创建所需的 SQLite 数据库文件

### 数据存储

插件使用两个 SQLite 数据库文件：
- `players.sqlite3` - 存储玩家数据
- `state.sqlite3` - 存储游戏状态

数据库文件位于 `data/plugin_data/astrbot_plugin_slg/` 目录下。

## 扩展开发

### 添加新角色

在 `characters/character.json` 中添加新的角色定义：

```json
{
  "name": "角色名",
  "title": "称号",
  "background": "背景描述",
  "skills": [
    {
      "name": "技能名",
      "description": "技能描述"
    }
  ]
}
```

### 修改地图

编辑 `map/three_kingdoms.json` 文件来修改地图数据，包括：
- 添加或修改城市
- 调整城市位置
- 修改城市间的连接关系

### 添加新功能

1. 在 `domain/` 目录下创建新的服务类
2. 在 `domain/ports.py` 中定义必要的端口
3. 在 `infra/` 目录下实现对应的适配器
4. 在 `app/container.py` 中注册新服务
5. 在 `main.py` 中添加新的命令处理

## 注意事项

- 插件会自动进行资源结算，无需手动操作
- 迁城功能每天只能使用一次
- 战斗系统目前为测试版本，不实际结算战损
- 抽卡系统有保底机制，前5次免费

## 贡献

欢迎提交 Issue 和 Pull Request 来改进这个插件。
本插件处于开发阶段，欢迎加入qq群：1054962131 进行讨论和建议
## 许可证

MIT License
