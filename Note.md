
———0814———
一些日程模块可能的未来设想
1. 用挂机类玩法的皮承载常驻关注信息的入口
2. 玩法逐步解锁功能，也是方便用户逐渐学习使用，要解锁的模块可以挑，一天内可以换一次或换回来。
3. 对于一些过于个性化的标签，考虑到内容是需要分享的，就需要一个替代名称/替代类型；要不要用是一个开关。
4. 当天的周期性项目的优先级也高一点，多次唤醒
5. 对于洗面奶来说，这是一个指标类瞬间事件，有一个degree是检查数值，有一个degree是开启新洗面奶，还有一个是用完？总之用这个逻辑吧。
6. 指标类事件需要复杂的管理规则和容器，这就开始到精力和优先级了，比如这一个时间到底做什么
7. 同样的，还有一个复杂的规则是未来到期，比如应缴帐款，过期的牛奶（不同的批次，同一个管理入口），优惠券；对过期没用完的也给一个评估，现在界面tag不太足，这个要看看怎么规划，可能打个勾八
8. 用持续更新的卡片异步地追加AI的反馈内容？比如第一个功能的备选，此时后台还在尝试做第二个功能参数的解析？
9. 未来这个属性和事件类型的解耦，以及真的是一次性未来备忘的Future系列临时ID
10.开发他人使用需要
10.1)先注册一个新的实体，测试验收，迁移数据
10.2)完成id和默认日报参数的设置
10.3)需要一个事件定义维护卡片
11.可能的数据储存和读取结构，json vs tmol/txt？ vs 轻量数据库？
12.很可能在飞书里，表单型数据没办法主动回调回收用户的数据，因为是客户端信息

13.event degree这两个层级搭配控制开关就是考虑聚合与否和完成方式与否，比如用餐里的degree零食会把用餐的周期全弄坏了，但这个显然应该是event事件
14.在duration里增加degree的预估时间，并可以跟随选择切换
15.季度、月度分析和周分析要有一定程度的MECE规划；比如每个季度可能就要反思一下某些自己想要的方向是不是真的够好
16.只有记录不够，还需要一个每2小时的个人状态，这样才有强驱动——但这个等先跑通了点餐和思考。
17.对Future类事件的非完成编辑，比如改时间，这个显然需要一个独立按钮；以及如果有未来到期这个情况，Future可能要从类型变成属性，有未来到期的事情本身可能跟也是一个重复事件，比如每月2日的房贷？所以还是那句话，属性和类型要分开。
18.在筛选没有的情况下增加一个列出所有名字和在该类型下注册新事件的按钮
19.还是要再体会和思考一下瞬间开始和开始的交互逻辑问题


    "新的沐浴露_00001": {
      "event_name": "新的沐浴露",
      "create_time": "2025-08-10 14:27",
      "note": "多芬，草莓味，400g-用了0.1就扔了，不好闻",
      "progress_value": 1.0,
      "record_id": "新的沐浴露_00001",
      "duration": 5,
      "end_time": "2025-08-15 21:28"
    },

这里的duration和progress_value都是问题，还是完成和目标值的情况，实际上新的沐浴露的瞬间就已经完成了
比如沐浴露剩余量
关联新的沐浴露 1.0？
关联物资管理-检查
关联用完

包括这个长时间段还影响了原子时间的归属和预估时间，先手动修改回避一下，准备睡觉
手动改完因为结束时间结果把所有后续记录的查询都隔断了……有序列表也很难绷，等跑通了还是要用数据库，至少给人用之前吧？
或者加一个按时间排序的整理功能——这个应该更低频


认知负荷追踪：记录每次活动切换时的"疲劳感"(1-5分)
情绪标签：在note中加入简单情绪词 (兴奋/平静/焦虑/满足)

用place holder来传递状态信息，比如默认值，或者当前生效值？

【文档编辑】
飞书的卡片都需要提供一个直接跳转到原始文档的链接，方便直接编辑。而且要有一个相对干净的同步机制——点击进去之后分别好几次监听一下。

等开始编辑文档了，也要多用用vibe code对md文档的修改？不过rag还是有些代价开销的……包括替换和编辑？grep也很重要，包括一致的措辞？
新增和汇总的区别，新增的部分是一个新增，这一条是可以独立RAG的，汇总是另一个东西，一段时间重建？

rag的chock是用来做向量匹配，关键词则是关键词，出处是出处，编辑是编辑。
我可以先不用edit_tool这个聪明的做法，而就是每个都全文重写？

取到的信息需要包括出处，位置，内容。然后相关的编辑则是输入了新内容，编辑和整合认知
最后把编辑好的部分diff出来，并预览——卡片？

a. 在微信小程序做一个简单的查阅——但是用外部参数控制界面，等啥时候做好了就切换成聊天界面？
b. 对于特定的分组话题可以从文档里获取反馈，但汇编还是要另外的节奏

edit-find-replace 参考开源项目的逻辑
8.3k stars https://github.com/charmbracelet/crush
26.4k stars https://github.com/voideditor/void/blob/34e3413d/VOID_CODEBASE_GUIDE.md
https://deepwiki.com/search/agent_0e9c5727-90e0-48f0-a1e5-6b30c6a50deb

source
https://microsoft.github.io/monaco-editor/
https://github.com/yayxs/ai-coding?tab=readme-ov-file
https://metaso.cn/search/8642237008977645568

————————


## 一些备忘

花点时间清理AI给的粗糙框架

——————0629———————
层级
前端
router
service
pending & schedule -> automatic

handler 是前端的信息
去掉前端特征的信息之后，进入router
然后就到了processor/service

adapter

 process

  service

normal service return

 card_manager

pending service return

 messgae modify



对于pending来说，这里和注册adapter逻辑一样，需要知道的信息是adapter name/ operation method name
自驱动的信息除了原本添加的confirm action外，还有 adapter action，这部分可以生成的时候指定，并且在一开始注册的时候就有一套默认方法？
先不动。
_register_ui_update_callbacks


一个operation 默认关联几个前端是不是也应该配置控制，前端可以另外改，比如set only之类的，不然多前端之后的管理就麻烦了
对于operation来说支持的前端方法是一个清单，adapter 和 handler的指令？

解析不应该通用，数据要通用的塞到payload里


pengding和schedule才是最后一个板块
message 更新用户 82205 2 之后得到的后端信息应该是
业务 update_user
参数 82205 2
需要pending，30秒——来自配置？
默认确认——来自配置

然后返回的是一个 pending operation info 或者 function call info
前端要根据必要的步骤比如message，和pending里operation 注册信息进去，operation需要能够set一些信息和adapter信息
换言之operation就是最外层的，因为要能够调用前端

理想的card_action都不需要用message_processor分发，因为对应的cards.py里已经属地化的包含了业务，除非是比较旧的
这里的card_action要为了解耦做准备，所以就是特地分离前后端，这样别的前端也可以调用，而不用去用耦合的方法
理解了Notion的数据结构逻辑，为什么要有一个type，又要有一个字段名，就是用type作为key直接去取

就和卡片需要用配置一样，业务也需要用配置驱动，但这个后话，在这个之前就只能硬编码了
但可以减少层级

=======0629=======


外部数据源看起来是不太行，打不通。
先从日常开始吧，天气，日程，rooter？还有B站功能迁移

B站按钮后续增加一个全部已读，以及随机抽取，+选择范围，默认是10分钟？

用类似MCP的规范来做router吗？这样可能会好一点

所谓可撤销的缓存业务=没有真实提交，但是查询的时候又可以和正式数据合并在一起，这样一来一般也就缓存1-2份数据，这样还要不要有一个定时，也是有必要的，
因为没必要一直缓存，可以用一个半小时的循环来检查是不是有超过半小时的缓存，超过的就写入了。
用户也可以根据下面的跟随气泡快速修改发证机关。点击和打字编辑效果一致——意味着需要开启上下文模式，但这个最好可以用消息评论的串，减少管理的复杂度——或
者至少要验证一下消息的id和回复消息的逻辑

对于酒馆战棋这种版本的逻辑，为了呼应思考，至少可以有一个非全局的领域开关，只在这里更新——也就是默认全局不读取，需要主动引用，或者被概率抽到。
但是对于文档的部分，我可能需要一个可视化的地方，飞书文档应该就是另一个比较好的储存和编辑位置？需要一个结构来储存。

TTS的识别也是要先查看消息结构，是不是包括文字，但这里需要保留的是原始信息，方便回听，这就是闪念胶囊了。

第一轮意图识别确实可以包括功能调用，但是功能调用是应该有确切的清单，除此之外就一定要排除功能调用——比如“做一个示例文件”，如果没有“创建文件”这个功
能，那就是一个待办事项

I am a creative and strategic leader with a passion for crafting immersive game experiences. As a game designer and CEO, I have honed
my skills in project management, team leadership, and communication while directing the strategic vision of an AI consulting
organization. My experience in narrative design and player engagement analysis allows me to create compelling storylines that
resonate with players. Driven by a desire for continuous learning and a deep interest in education and self-development, I am
constantly seeking new ways to innovate and improve the player experience. I leverage my expertise in Python and strategic planning
to guide development teams and cultivate strong client relationships, ensuring that every project is a success.

数字分身天然就要包括多个自己，除了主体之外还有其他几个预设槽位

1. 卡片置顶和pin？的验证，用来做一个看板，实在不行也可以第一个消息用话题，后面的回复就引用，可以3次操作点到话题里面————还有标签页，总之交互手段都要测试一下有什么信息
2. 还是要验证获取消息和组装的策略，并且整合一个开关，确定是闲聊还是记录——闲聊的优先级低一些，需要开关
3. B站更新的指令要整合在B站前面，这样可以主动触发

gradio的扫码能力和回调处理？二维码作为链接和参数入口 主要是脱离飞书确实有点鉴权的问题。晚些再看吧

切换模式就用chat 和 agent就好了诶！ chat的也有上下文就是聊天，可以在指令一开始的时候触发，然后这里就会进入chat话题，上面还有一个chat的卡片置顶？

临时的这个模式要放在项目里，但最好可以剪切拆卸，追求都封装到一个模块里？

这些思考就需要有各种各样的容器来由AI识别，比如最近编辑的，看起来我可以处理最近3个？这个应该就会比较接近

关于每2小时的循环和每周、每月的循环，以及现在的pending循环的重叠和解耦的关系
虽然业务上消息是独立的，但我毕竟不希望自己被信息轰炸，而是有一个完整的汇总。


我的钱和其他人的钱差不多，所以买东西没有差别；但我的时间和其他人的时间差很多，应该多买别人的时间
——>日常的基础agent应该就是yes and的那个思考助理


________

检查富文本的消息？—message_type为post，感觉可以先不去解析
2025-06-22 15:46:32,661 DEBUG { 'challenge': None,
  'event': { 'message': { 'chat_id': 'oc_00da7eba51fbc1fdcf5cf40ab332bf7e',
                          'chat_type': 'p2p',
                          'content': '{"title":"写个小作文","content":[[{"tag":"text","text":"重新刷新prompt","style":[]}],[{"tag":"img","image_key":"img_v3_02ng_f530c621-511e-4155-885f-84327da9255g","width":850,"height":1188}]]}',
                          'create_time': '1750578393311',
                          'mentions': None,
                          'message_id': 'om_x100b4a4f035f60b80f37721ad0ea286',
                          'message_type': 'post',
                          'parent_id': None,
                          'root_id': None,
                          'thread_id': None,
                          'update_time': '1750578393311',
                          'user_agent': None},
             'sender': { 'sender_id': { 'open_id': 'ou_08158e2f511912a18063fc6072ce42da',
                                        'union_id': 'on_f30d6f403ec60cad71c6c9c1e1da1ce0',
                                        'user_id': None},
                         'sender_type': 'user',
                         'tenant_key': '101c4da96edf975e'}},
  'header': { 'app_id': 'cli_a6bf8e1105de900b',
              'create_time': '1750578393583',
              'event_id': 'e076931bdbe7eda2f26c0bafe475c7c7',
              'event_type': 'im.message.receive_v1',
              'tenant_key': '101c4da96edf975e',
              'token': ''},
  'schema': '2.0',
  'token': None,
  'ts': None,
  'type': None,
  'uuid': None}

pin和置顶没消息

任务是一个消息，点击完成任务不是消息
2025-06-22 15:53:30,857 DEBUG 🔍 P2ImMessageReceiveV1对象详细信息 (pprint):
2025-06-22 15:53:30,857 DEBUG { 'challenge': None,
  'event': { 'message': { 'chat_id': 'oc_00da7eba51fbc1fdcf5cf40ab332bf7e',
                          'chat_type': 'p2p',
                          'content': '{"task_id":"96dba4b6-1fe7-4ce4-abd5-fbdf7344671a","summary":{"title":"","content":[[{"tag":"text","text":"增加卡片导入","style":[]}]]},"due_time":"1750550400000"}',
                          'create_time': '1750578811485',
                          'mentions': None,
                          'message_id': 'om_x100b4a4f29785fe40f38a30d3d08f8e',
                          'message_type': 'todo',
                          'parent_id': None,
                          'root_id': None,
                          'thread_id': None,
                          'update_time': '1750578811485',
                          'user_agent': None},
             'sender': { 'sender_id': { 'open_id': 'ou_08158e2f511912a18063fc6072ce42da',
                                        'union_id': 'on_f30d6f403ec60cad71c6c9c1e1da1ce0',
                                        'user_id': None},
                         'sender_type': 'user',
                         'tenant_key': '101c4da96edf975e'}},
  'header': { 'app_id': 'cli_a6bf8e1105de900b',
              'create_time': '1750578811799',
              'event_id': 'bb8c2ecdde189373ecb4d0d04c97fbbc',
              'event_type': 'im.message.receive_v1',
              'tenant_key': '101c4da96edf975e',
              'token': ''},
  'schema': '2.0',
  'token': None,
  'ts': None,
  'type': None,
  'uuid': None}
2025-06-22 15:53:30,857 DEBUG   - 关键信息: 此消息非回复消息 (parent_id is None or empty)


AdminProcessor._execute_user_update_operation()
    ⬅️ PendingCacheService.confirm_operation()
    ⬅️ AdminProcessor.handle_pending_operation_action()
    ⬅️ MessageProcessor._handle_pending_admin_card_action()
    ⬅️ MessageProcessor.action_dispatchers["confirm_user_update"]
    ⬅️ PendingCacheService.timeout_handler (默认动作触发)
    ⬅️ PendingCacheService.create_operation() (30秒后自动执行)
    ⬅️ AdminProcessor._create_pending_operation()
    ⬅️ AdminProcessor.handle_update_user_command()
    ⬅️ "更新用户 82205 2"

n.最后层
admin._execute_user_update_operation——业务提交
	业务前信息
		operation的object，包含user_id、user_type
	业务后信息
		无，只有一个日志

……省略……

2.AdminProcessor._create_pending_operation
	业务前信息
		context-沿用
		business_id-由上一个步骤指定
		operation_data-来自user_msg的预处理
	业务后信息

		full_operation_data-dict object容器
			**operation_data，继承原始信息
			finished、result，【新增，为了控制卡片的参数
			hold_time，从timeout_text格式化来，也是为了控制卡片的参数，但信息来自配置cards_business_mapping的timeout_seconds
			operation_type，来自business_id，这样和上一层正好相反，总之就是概念没统一
			_config_cache，一些为后续业务提前采集的数据对象
				business_config，特定当前business_id对应的cards_business_mapping里的business_mappings配置
				card_config，特定当前business_id对应的cards_business_mapping里的card_configs配置
				template_info，特定当前business_id对应的cards_business_mapping里的card_configs配置里的template_id和template_version，用来引用特定版本的飞书卡片模板，至少在信息必要性上是不必要的
				reply_mode，特定当前business_id对应的cards_business_mapping里的card_configs配置里的reply_modes，至少在信息必要性上是不必要的
				card_config_key，特定当前business_id对应的cards_business_mapping里的business_mappings配置里的card_config_key，至少在信息必要性上是不必要的
		pending_cache_service.create_operation 增加一个缓存操作，如果缓存时间为0就是直接执行
			user_id，来自context.user_id
			operation_type，来自business_id——这里也是概念没统一
			operation_data，来自方法内处理的full_operation_data
			admin_input，来自operation_data的admin_input，这里出现了两个含义不同的operation_data，不是最佳实践
			hold_time_seconds，来自配置 cards_business_mapping
			default_action=【新增，手动设定的默认确认，可以属性化
		return ProcessResult.success_result，提交信息回到最外层的handle，进入 message._handle_special_response_types——卡片的另一条业务线，回复模式目前也是来自配置cards_business_mapping的response_type，这里的关系就比较好，不展开了
	评价
		看起来澄清了不少定义，但一来有混乱，而来有一些不必要的复杂度

1.外层路由入口
AdminProcessor.handle_update_user_command
	业务前信息
		context，标准格式的上下文
		user_msg，用户输入的内容
	业务后信息
		context-沿用
		OperationTypes.UPDATE_USER【新增，指定的配置关联——映射到_create_pending_operation的business_id，配置测对应business_mappings的keys
		dict——映射到_create_pending_operation的operation_data
			dict_user_id，来自user_msg的转换
			dict_user_type，来自user_msg的转换
			dict_user_admin_input，来自user_msg的转换
		-user_msg原始信息丢失，但context还有
	评价
		感觉businessid和operation的概念没统一，dict在这里的预处理没问题

0.顶层路由
handle_admin_command
	业务前信息
		context，标准格式的上下文，期待包含了业务的所有消息
		user_msg，用户输入的内容，来自 context.content，这层冗余到不是不能接受？
	业务后信息
		handle_update_user_command	【新增，路由性质，但包含了业务信息，根据特定的关键词匹配指定，这里可以接受指定，因为暂时还没打算制作完整的指令和功能映射
		context-沿用
		user_msg-沿用


schedule、pengding、aggreation，这些或许才是service层，processor就是processor——router只到processor，  最外层的main和handler调用pending等？
总之现在的shcedule的两个模块要整理，可以等做完之后。

————0709————


8.关于思考和分析，这部分还是需要依托飞书文档或者markdown，但考虑到diff的问题，markdown应该简单一些，具体要看飞书的验证情况



水晶球的多个备选也是异步来增加的，不要一开始就算进去——添加到一个队列里？作为一个持续更新的卡片，输入和刷新的问题要看一看。
开始的清单，要能关闭

中指的指甲——水晶球，添加到to do的健康检查里？是一个事项————有一个专属的输入入口，可以做AI接管
不过这个要单独做一个按钮？可以从文本长度来做判断？


习惯追踪 airtable

重要踩坑备忘
1.P2CardActionTriggerResponse刷新是一个弱兼容强检测的场景，所有刷新失败一定都是语法错误——但发送则未必这么强检测错误。
双重json.dump的内置方法打印出来去飞书上检查

sender再坚持一下

card_action_data这个结构对AI来说识别能力很差，也不会当做上下文，要自己主动说明引导尝试一下，否则就要自己看。

tag
超多的问题先做盘点，再做估算，最后调整
可能要削减第二层级的逻辑，误操作的比例不高。
点击之后第二层级就去掉其他无关？能有多少收益呢。——类型筛选是一个比较大的吃亏的地方。 8%左右

button*2
column_set的结构或许有调整和优化空间

折叠架构 3
标题+输入组合 6

form 的3个按钮（无法省略）
12（1+4+3+4）

新定义的92个不能省略——加上选项可能更多。
____
# 装饰器使用心得

## 问题分析

### 当前装饰器的问题
1. **错误信息模糊**：`@safe_execute` 装饰器捕获了所有异常，但只显示装饰器定义的错误消息，丢失了原始错误信息
2. **调试困难**：无法准确定位错误发生的具体位置和原因
3. **错误堆栈丢失**：装饰器重新抛出异常时，丢失了原始的错误堆栈信息

### 错误示例
```
2025-07-29 21:30:52,904 ERROR 🔴 业务处理异常 创建每日信息汇总失败 [daily_summary]: too many values to unpack (expected 2)
```
这个错误信息告诉我们：
- 错误发生在 `daily_summary` 方法中
- 具体错误是 "too many values to unpack (expected 2)"
- 但无法知道是在哪一行代码发生的

## 更好的做法

### 1. 分层错误处理
```python
# 业务层：只处理业务逻辑错误
def business_method():
    try:
        # 业务逻辑
        pass
    except BusinessException as e:
        # 处理业务异常
        return ProcessResult.error_result(str(e))
    except Exception as e:
        # 记录技术异常，但不重新包装
        debug_utils.log_and_print(f"技术异常: {e}", log_level="ERROR")
        raise

# 装饰器：只处理技术异常
@safe_execute("业务方法执行失败")
def decorated_method():
    return business_method()
```

### 2. 增强装饰器
```python
def safe_execute(error_message: str):
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # 保留原始错误信息
                full_error = f"{error_message}: {str(e)}"
                debug_utils.log_and_print(full_error, log_level="ERROR")
                # 记录错误堆栈
                import traceback
                debug_utils.log_and_print(f"错误堆栈: {traceback.format_exc()}", log_level="ERROR")
                return ProcessResult.error_result(full_error)
        return wrapper
    return decorator
```

### 3. 调试友好的做法
- 在关键方法中添加详细的日志
- 使用 try-except 包装可能出错的代码块
- 记录详细的错误上下文信息
- 避免在装饰器中丢失原始错误信息

## 当前解决方案
在 `daily_summary` 方法中添加了详细的日志，帮助定位 "too many values to unpack" 错误的具体位置。