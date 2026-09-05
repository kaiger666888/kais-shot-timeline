<!-- 2026-09-03 Kai 质疑：批量臂为何用 Turbo 4-step 而非 KMC 定案预览档 -->

# 定谳（Kai 质疑成立，两层错误）

## 根因
batch_render_ep01.py（09-02 建）从 S89 单镜闭环克隆了「v4 中奖配方」= T8 Turbo 4-step
（LoRA minimax_h3_turbo_4step_original / res_multistep / shift_video=12 / 直连 :8188 绕过 KAP），
未跟随两笔平台定案：
- 08-31 blind3 盲测定案：preview/final 统一 lightx2v-8-768p 9步（与成片同链同 LoRA）
- 09-02 KAP 修正：turbo 移出 H3_EXPOSED_PROFILES 白名单（默认关闭，仅显式 turbo=true 直调）

错误叠加三层：①引擎过时（继承不到 KAP fix2）②smoke3 页标签写「LightX2V 4-step」双重失实
（既非 LightX2V 家族也非 9 步）③放量门（smoke3）引擎与平台定案不一致无人核验即交付。

唯一合理成分：GSRT「prompt 唯一变量」纪律——S89 prompt 对着 turbo 配方调的。
但正确做法 = 引擎 A/B 一起端盲选，不是放量前不换。

## 已执行修正（09-03 上午）
1. smoke3 页标签「LightX2V 4-step」→「Turbo 4-step」（4 处）
2. 新脚本 batch_render_ep01_lightx2v9.py：同 seed(990202)/prompt/条件帧/音窗，
   唯一变量=引擎 → lightx2v-8-768p（LoRA fl2v_turbo_8step_v1.0_768p / 9步 / euler / shift=6 /
   LoraLoaderModelOnly 非 Bypass），重渲 s064/s089/s092 全过（6.0/6.0/15.9min）
3. 内嵌元数据取证：新臂 LoRA/sampler/steps/shift 四项全实锤（五层出身链第5层）
4. 三臂对比页（GT+旧臂+修正臂，锁步+全屏+原声）：
   /home/kai/shared/2026-09-03/ep01_engine_ab_compare.html
   http://100.124.72.88:8082/2026-09-03/ep01_engine_ab_compare.html

## 待 Kai 决策
- 三臂盲测后：93 镜放量用哪臂（推荐=盲测定案档 lightx2v-8-768p 9步）
- 放量前把 batch_render 脚本引擎参数化（--engine turbo|lx9），避免配方再次漂移于平台定案
