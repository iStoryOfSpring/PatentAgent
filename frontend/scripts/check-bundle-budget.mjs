import { readdirSync, readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";

const budgetBytes = 200 * 1024;
const directory = new URL("../dist/assets/", import.meta.url);
const oversized = [];

for (const name of readdirSync(directory).filter(name => name.endsWith(".js"))) {
  const compressed = gzipSync(readFileSync(new URL(name, directory))).byteLength;
  if (compressed > budgetBytes) oversized.push({ name, compressed });
}

if (oversized.length) {
  for (const item of oversized) {
    console.error(`${item.name}: ${(item.compressed / 1024).toFixed(2)} KiB gzip exceeds 200 KiB`);
  }
  process.exit(1);
}

console.log("bundle budget passed: every JavaScript chunk is <= 200 KiB gzip");
