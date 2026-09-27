# 来源、许可和改动说明

## 机械模型

原始机械臂模型：**Robotic Arm with a base for components**，作者 **Arun Kumar**。

- 来源：https://www.printables.com/model/1596575-robotic-arm-with-a-base-for-components
- 基座等改版资料署名：**RACBOTS**
- 原资料标注许可：**Creative Commons Attribution-ShareAlike 4.0 International**

仓库中的原模型、修改后的 STL/3MF/Blender 文件、渲染图和相关几何修改脚本按 CC BY-SA 4.0 的署名与相同方式共享要求发布。再次分发或继续修改时，应保留原作者、改版来源、本仓库改动说明和同一许可证。

## Arduino 代码

原始 Arduino 项目文件中的版权说明署名 **Tech Talkies YouTube Channel**。

- 频道：https://www.youtube.com/@techtalkies1
- 相关视频：https://www.youtube.com/watch?v=Qdebit3DgCE

取得的上游代码没有随附明确的开源许可证。仓库保留其版权说明与来源，不声明取得超出原作者授权范围的权利，也不把 CC BY-SA 4.0 自动套用于该代码。需要复制、再发布或商用代码时，应向原作者确认授权条件。

## 本仓库的主要修改

- XIAO ESP32-S3 引脚适配。
- 四关节软限位与渐进运动。
- 可持久化 Home 姿态及相关 HTTP API。
- 新的嵌入式网页控制台和本地模拟预览。
- 舵盘槽、MG90S 避让和摄像头支架等结构改版。

具体日期与范围见 `CHANGELOG.md` 和各修改目录中的说明文件。
