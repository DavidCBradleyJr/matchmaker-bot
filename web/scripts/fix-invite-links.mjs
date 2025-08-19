// scripts/fix-invite-links.mjs
import { promises as fs } from "node:fs";
import { join } from "node:path";
import { execSync } from "node:child_process";

// 1) find matching files via ripgrep (rg)
function findFiles() {
  const cmd =
    `rg -l "https://discord\\.com/oauth2/authorize\\?client_id=NEXT_PUBLIC_DISCORD_CLIENT_ID&scope=bot\\+applications\\.commands" web || true`;
  const out = execSync(cmd, { stdio: ["ignore", "pipe", "inherit"] })
    .toString()
    .trim();
  return out ? out.split("\n") : [];
}

// 2) transform content with minimal changes
function transform(src) {
  // exact string we expect to fix
  const bad =
    "https://discord.com/oauth2/authorize?client_id=NEXT_PUBLIC_DISCORD_CLIENT_ID&scope=bot+applications.commands";

  const good =
    "`https://discord.com/oauth2/authorize?client_id=${process.env.NEXT_PUBLIC_DISCORD_CLIENT_ID}&scope=bot%20applications.commands`";


  const pattern = new RegExp(
    `(["'])${bad.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\$&")}\\1`,
    "g"
  );

  let updated = src.replace(pattern, good);

  if (updated === src && src.includes(bad)) {
    updated = src.split(bad).join(good);
  }

  return updated;
}

async function run() {
  const files = findFiles();
  if (!files.length) {
    console.log("No files found with the hard-coded OAuth URL. Nothing to do.");
    return;
  }

  console.log(`Found ${files.length} file(s). Writing full updated copies (*.updated):\n`);
  for (const file of files) {
    const orig = await fs.readFile(file, "utf8");
    const next = transform(orig);

    if (next === orig) {
      console.log(`- ${file}: skipped (no change after transform)`);
      continue;
    }

    const outPath = `${file}.updated`;
    await fs.writeFile(outPath, next, "utf8");
    console.log(`- ${file} -> ${outPath}`);
  }

  console.log(
    `\nReview the *.updated files. If they look good, replace originals:\n\n` +
    `for f in $(rg -l "https://discord\\.com/oauth2/authorize\\?client_id=NEXT_PUBLIC_DISCORD_CLIENT_ID&scope=bot\\+applications\\.commands" web); do \n` +
    `  mv "$f.updated" "$f";\n` +
    `done\n`
  );
}

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
