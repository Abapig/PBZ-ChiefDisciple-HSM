# 第二步工程补全交付

阅读顺序：

1. `概率检查器.html`：离线交互比较四阶段、不同距离、实时压力与历史学习。
2. `战斗决策工程规格.md`：完整公式、采样归因、协同、通用动作、阶段与异常处理。
3. `逐招参数与概率表.md`：33根招式的全部基础参数、模板与例子。
4. `模拟与核对报告.md`：本次实际测试、统计结果、修正与局限。

可执行代码：`catalog.py`（配置）、`policy.py`（算法参考）、`verify.py`（测试和模拟）、`build_review.py`（从结果生成展示材料）。JSON/CSV 为生成结果，不要手工修改后与代码脱节。

从项目根目录运行（Python 3.10+，仅标准库）：

```powershell
& 'D:\Program Files\Unreal\UE_5.8\Engine\Binaries\ThirdParty\Python3\Win64\python.exe' -B Research/Step2/Engineering/verify.py
& 'D:\Program Files\Unreal\UE_5.8\Engine\Binaries\ThirdParty\Python3\Win64\python.exe' -B Research/Step2/Engineering/build_review.py
```

本目录不修改UE资产，不绑定模型、动画或碰撞。此轮为第二步的量化设计和验证；完整HFSM图及单页蓝图实现仍按既定阶段验收后开展。
