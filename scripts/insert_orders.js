const { createClient } = require('@supabase/supabase-js');
const ws = require('ws');
const fs = require('fs');
const path = require('path');

const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_KEY;
const START_CHUNK = parseInt(process.env.START_CHUNK || '0');
const END_CHUNK = parseInt(process.env.END_CHUNK || '-1');
const MANIFEST_PATH = process.env.MANIFEST_PATH || 'data/manifest.json';
const DATA_DIR = process.env.DATA_DIR || 'data';

if (!SUPABASE_URL || !SUPABASE_SERVICE_KEY) {
  console.error('❌ SUPABASE_URL, SUPABASE_SERVICE_KEY 필요');
  process.exit(1);
}

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY, {
  realtime: { transport: ws }
});

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function insertChunk(records, idx, retries = 3) {
  for (let attempt = 1; attempt <= retries; attempt++) {
    const { error } = await supabase.from('pre_orders').insert(records);
    if (!error) return { success: true, count: records.length };
    if (attempt < retries) { await sleep(2000 * attempt); }
    else return { success: false, error: error.message };
  }
}

async function main() {
  const manifest = JSON.parse(fs.readFileSync(MANIFEST_PATH, 'utf8'));
  const totalChunks = manifest.total_chunks;
  const endChunk = END_CHUNK === -1 ? totalChunks - 1 : Math.min(END_CHUNK, totalChunks - 1);

  console.log(`📦 ${manifest.total_records.toLocaleString()}건 / ${totalChunks}개 청크`);
  console.log(`🎯 chunk ${START_CHUNK} ~ ${endChunk}`);

  let totalInserted = 0, totalFailed = 0;
  const failedChunks = [];
  const startTime = Date.now();

  for (let i = START_CHUNK; i <= endChunk; i++) {
    const fname = path.basename(manifest.files[i]);
    const filePath = path.join(DATA_DIR, fname);
    if (!fs.existsSync(filePath)) { console.warn(`⚠️ 파일 없음: ${filePath}`); continue; }

    const records = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    const result = await insertChunk(records, i);

    if (result.success) {
      totalInserted += result.count;
      const pct = (((i - START_CHUNK + 1) / (endChunk - START_CHUNK + 1)) * 100).toFixed(1);
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(0);
      if ((i - START_CHUNK) % 20 === 0 || i === endChunk)
        console.log(`✅ [${i}/${endChunk}] ${totalInserted.toLocaleString()}건 | ${pct}% | ${elapsed}s`);
    } else {
      totalFailed += records.length;
      failedChunks.push(i);
      console.error(`❌ [${i}] ${result.error}`);
    }
    if ((i - START_CHUNK + 1) % 10 === 0) await sleep(300);
  }

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  console.log(`\n✅ 삽입: ${totalInserted.toLocaleString()}건 | ❌ 실패: ${totalFailed}건 | ⏱ ${elapsed}s`);

  const { count } = await supabase.from('pre_orders').select('*', { count: 'exact', head: true });
  console.log(`📊 DB 총 레코드: ${count?.toLocaleString()}건`);

  if (totalFailed > 0) process.exit(1);
}

main().catch(e => { console.error(e); process.exit(1); });
