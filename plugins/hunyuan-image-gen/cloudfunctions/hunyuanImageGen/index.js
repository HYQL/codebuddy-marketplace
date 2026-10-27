const tcb = require('@cloudbase/node-sdk');

// 仅从环境变量读取环境 ID（部署时通过 envVariables.TCB_ENV 注入），不硬编码任何真实 envId
const ENV_ID = process.env.TCB_ENV;

// 已启用模型组（DescribeAIModels 确认 Status=1、EnableMCP=true）
const CAPABILITY_GROUP = 'hunyuan-image';
// 文生图：能力组别名，命中同一 AI 生图额度包
const T2I_MODEL = process.env.HUNYUAN_MODEL || 'hunyuan-image';
// 图生图：完整模型 id（DescribeAIModels 确认可用）
// ⚠️ 该 3.0 模型将于 2026-12-01 00:00 下线，接替模型 hy-image-v3.5-preview 调用方式不同，上线前需预留迁移
const I2I_MODEL = 'HY-Image-v3.0-I2I-ToB-v1.0.1';

exports.main = async (event = {}, context) => {
  const prompt = (event && event.prompt) || '一只赛博朋克风格的猫';
  const size = (event && event.size) || '1024x1024';
  const n = (event && event.n) || 1;

  // 垫图（二选一）：URL 优先，其次 base64；先做清洗与校验
  const imageUrl = ((event && event.imageUrl) || '').toString().trim();
  const imageBase64 = ((event && event.imageBase64) || '').toString().trim();

  const hasRef = Boolean(imageUrl || imageBase64);
  if (hasRef && Boolean(imageUrl) === Boolean(imageBase64)) {
    throw new Error('I2I 垫图请只提供 imageUrl 或 imageBase64 之一');
  }

  // 传入垫图即走图生图（I2I），否则文生图（T2I）
  const isI2I = hasRef;
  const model = (event && event.model) || (isI2I ? I2I_MODEL : T2I_MODEL);

  const app = tcb.init({ env: ENV_ID });
  const imageModel = app.ai().createImageModel(CAPABILITY_GROUP);

  const payload = { model, prompt, size, n };
  if (isI2I) {
    // I2I 专有垫图参数（图生图模型额外支持），最多 1 张、≤10MB、jpg/jpeg/png
    if (imageUrl) payload.image_urls = [imageUrl];
    else payload.images = [imageBase64];
  }

  const res = await imageModel.generateImage(payload);

  const data = (res && res.data) || [];
  const urls = data.map((d) => (d && d.url) || '').filter(Boolean);
  const revised = data.map((d) => (d && d.revised_prompt) || '').filter(Boolean);
  if (!urls.length) {
    throw new Error('未返回图片 URL: ' + JSON.stringify(res).slice(0, 1000));
  }
  return { ok: true, mode: isI2I ? 'i2i' : 't2i', model, urls, revised_prompt: revised };
};
