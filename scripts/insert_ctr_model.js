const { createClient } = require('@supabase/supabase-js');
const ws = require('ws');
const fs = require('fs');
const path = require('path');

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_KEY,
  { realtime: { transport: ws } }
);

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  const manifest = JSON.parse(fs.readFileSync(process.env.MANIFEST_PATH, 'utf8'));
  console.log(`📦 ${manifest.total_records.toLocaleString()}건 / ${manifest.total_chunks}개 청크`);
  console.log(`🗂  테이블: ${manifest.table}`);

  let inserted = 0, failed = 0;
  const startTime = Date.now();

  for (let i = 0; i < manifest.total_chunks; i++) {
    const fname = path.basename(manifest.files[i]);
    const records = JSON.parse(fs.readFileSync(path.join(process.env.DATA_DIR, fname), 'utf8'));

    let error;
    for (let attempt = 1; attempt <= 3; attempt++) {
      const res = await supabase.from(manifest.table).upsert(records, { onConflict: 'ctr_code' });
      error = res.error;
      if (!error) break;
      await sleep(1000 * attempt);
    }

    if (!error) {
      inserted += records.length;
      if (i % 10 === 0 || i === manifest.total_chunks - 1) {
        const pct = ((i+1)/manifest.total_chunks*100).toFixed(1);
        console.log(`✅ [${i+1}/${manifest.total_chunks}] ${inserted.toLocaleString()}건 | ${pct}%`);
      }
    } else {
      failed += records.length;
      console.error(`❌ [${i}] ${error.message}`);
    }
    if ((i+1) % 10 === 0) await sleep(200);
  }

  console.log(`\n완료: 삽입 ${inserted.toLocaleString()}건 | 실패 ${failed}건 | ${((Date.now()-startTime)/1000).toFixed(1)}s`);
  const { count } = await supabase.from(manifest.table).select('*', { count: 'exact', head: true });
  console.log(`📊 DB 총 ${count?.toLocaleString()}건`);
  if (failed > 0) process.exit(1);
}

main().catch(e => { console.error(e); process.exit(1); });
