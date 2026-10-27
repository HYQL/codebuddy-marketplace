const tcb = require('@cloudbase/node-sdk');

// 仅从环境变量读取环境 ID（部署时通过 envVariables.TCB_ENV 注入），不硬编码任何真实 envId
const ENV_ID = process.env.TCB_ENV;
// 官方合规写法：createImageModel('hunyuan-image') 后 generateImage。
// 该组后端模型含 HY-Image-3.0-Plus-4090-Tob-v1.0，经网关映射；调用时 model 用 'hunyuan-image' 命中同一 AI 生图额度包。
const DEFAULT_MODEL = process.env.HUNYUAN_MODEL || 'hunyuan-image';

exports.main = async (event = {}, context) => {
  const prompt = (event && event.prompt) || '一只赛博朋克风格的猫';
  const size = (event && event.size) || '1024x1024';
  const n = (event && event.n) || 1;
  const model = (event && event.model) || DEFAULT_MODEL;

  const app = tcb.init({ env: ENV_ID });
  const imageModel = app.ai().createImageModel('hunyuan-image');
  const res = await imageModel.generateImage({ model, prompt, size, n });

  const data = (res && res.data) || [];
  const urls = data.map((d) => (d && d.url) || '').filter(Boolean);
  const revised = data.map((d) => (d && d.revised_prompt) || '').filter(Boolean);
  if (!urls.length) {
    throw new Error('未返回图片 URL: ' + JSON.stringify(res).slice(0, 1000));
  }
  return { ok: true, model, urls, revised_prompt: revised };
};
