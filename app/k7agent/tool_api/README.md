# Agent 请求接口（未接设备）

固定长度上限256字节，严格ASCII JSON子集。四个必填字段version/tool/args/ttl_ms；owner由可信调用方注入，事务ID由Dispatcher产生。模型不能提供DeviceEvent、完成状态或密码。

`{"version":1,"tool":"WifiStatus","args":{},"ttl_ms":1000}` 可解析为类型化只读请求；Capabilities同理。GimbalTarget保持Disabled，其余未接工具Unsupported。工具结果必须来自后续真实适配层，目前没有设备后端或Agent应用入口。

源码来自冻结parallel-robot-tools和tool-json-v1，未改变状态机；原始主机测试留在对应候选目录。本目录尚未列入固件构建，不表示自然语言理解或真实工具调用已完成。
