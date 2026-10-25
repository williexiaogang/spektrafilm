/* SpektraFilm Windows edition — GPLv3. See LICENSE in the repository root.
   Original color studies for the stock strip. Not measured science, and not
   artwork from any other film application. */

const FILM: Record<string, string> = {
  kodak_portra_160: "linear-gradient(145deg, #f7e2d2 0%, #e7b49a 42%, #8ec4c8 100%)",
  kodak_portra_400: "linear-gradient(145deg, #f4c9aa 0%, #d98b78 46%, #4f8f9a 100%)",
  kodak_portra_800: "linear-gradient(145deg, #e8b494 0%, #c56e66 48%, #3d7380 100%)",
  kodak_portra_800_push1: "linear-gradient(145deg, #dea07e 0%, #b85a56 50%, #315e6a 100%)",
  kodak_portra_800_push2: "linear-gradient(145deg, #c88868 0%, #9a4648 54%, #274852 100%)",
  kodak_gold_200: "linear-gradient(160deg, #ffe7a4 0%, #e39a3a 55%, #b55232 100%)",
  kodak_ultramax_400: "linear-gradient(155deg, #f0c56e 0%, #d06a3c 52%, #7a4038 100%)",
  kodak_ektar_100: "linear-gradient(140deg, #f2b89a 0%, #d24a3c 34%, #1f7a52 70%, #1a4e72 100%)",
  kodak_ektachrome_100: "linear-gradient(135deg, #e7f1f4 0%, #6ea8c4 48%, #2f6a58 100%)",
  kodak_kodachrome_64: "linear-gradient(150deg, #f0d2a8 0%, #c24132 40%, #1d6848 82%)",
  kodak_vision3_50d: "linear-gradient(140deg, #f4efe4 0%, #d8c09a 40%, #7f9cb0 100%)",
  kodak_vision3_250d: "linear-gradient(140deg, #ead8bc 0%, #c49862 48%, #3e6e90 100%)",
  kodak_vision3_200t: "linear-gradient(140deg, #ddd0ee 0%, #7a68ae 50%, #2c4a72 100%)",
  kodak_vision3_500t: "linear-gradient(140deg, #cbb6dc 0%, #5c4a8e 52%, #1e334e 100%)",
  kodak_verita_200d: "linear-gradient(148deg, #f6e4cc 0%, #d8a86e 50%, #6e96aa 100%)",
  fujifilm_pro_400h: "linear-gradient(150deg, #e7f4ee 0%, #7ec4ae 42%, #f0c4cc 100%)",
  fujifilm_provia_100f: "linear-gradient(140deg, #eef6f2 0%, #4e9a86 50%, #2e6288 100%)",
  fujifilm_velvia_100: "linear-gradient(148deg, #f6e2c4 0%, #d23c38 28%, #0e7a48 66%, #163e78 100%)",
  fujifilm_c200: "linear-gradient(158deg, #f6e4b0 0%, #e09440 58%, #a45a38 100%)",
  fujifilm_xtra_400: "linear-gradient(158deg, #f8d888 0%, #d07030 54%, #7a4034 100%)",
};

const PAPER: Record<string, string> = {
  kodak_portra_endura: "linear-gradient(180deg, #f7f1e6, #e4d0b8)",
  kodak_supra_endura: "linear-gradient(180deg, #f3eee4, #d5c4ae)",
  kodak_ultra_endura: "linear-gradient(180deg, #f8f4ee, #efe0cc)",
  kodak_ektacolor_edge: "linear-gradient(180deg, #f2eee6, #cfc2ae)",
  kodak_endura_premier: "linear-gradient(180deg, #f6f0e4, #e0ccb0)",
  kodak_2383: "linear-gradient(180deg, #1c1a18, #3a342c 62%, #6a5a48)",
  kodak_2393: "linear-gradient(180deg, #141210, #2a2622 58%, #8a6848)",
  fujifilm_crystal_archive_typeii: "linear-gradient(180deg, #f8f6f2, #e2dbd0)",
};

export const GHOST_FILMS: { id: string; name: string }[] = [
  { id: "kodak_portra_160", name: "Kodak Portra 160" },
  { id: "kodak_portra_400", name: "Kodak Portra 400" },
  { id: "kodak_portra_800", name: "Kodak Portra 800" },
  { id: "kodak_portra_800_push1", name: "Kodak Portra 800 (Push 1)" },
  { id: "kodak_portra_800_push2", name: "Kodak Portra 800 (Push 2)" },
  { id: "kodak_gold_200", name: "Kodak Gold 200" },
  { id: "kodak_ultramax_400", name: "Kodak Ultramax 400" },
  { id: "kodak_ektar_100", name: "Kodak Ektar 100" },
  { id: "kodak_ektachrome_100", name: "Kodak Ektachrome 100" },
  { id: "kodak_kodachrome_64", name: "Kodak Kodachrome 64" },
  { id: "kodak_vision3_50d", name: "Kodak Vision3 50D" },
  { id: "kodak_vision3_250d", name: "Kodak Vision3 250D" },
  { id: "kodak_vision3_200t", name: "Kodak Vision3 200T" },
  { id: "kodak_vision3_500t", name: "Kodak Vision3 500T" },
  { id: "kodak_verita_200d", name: "Kodak Verita 200D" },
  { id: "fujifilm_pro_400h", name: "Fujifilm Pro 400H" },
  { id: "fujifilm_provia_100f", name: "Fujifilm Provia 100F" },
  { id: "fujifilm_velvia_100", name: "Fujifilm Velvia 100" },
  { id: "fujifilm_c200", name: "Fujifilm C200" },
  { id: "fujifilm_xtra_400", name: "Fujifilm X-Tra 400" },
];

export const GHOST_PAPERS: { id: string; name: string }[] = [
  { id: "kodak_portra_endura", name: "Kodak Professional Portra Endura" },
  { id: "kodak_supra_endura", name: "Kodak Professional Supra Endura" },
  { id: "kodak_ultra_endura", name: "Kodak Professional Ultra Endura" },
  { id: "kodak_ektacolor_edge", name: "Kodak Ektacolor Edge" },
  { id: "kodak_endura_premier", name: "Kodak Professional Endura Premier" },
  { id: "kodak_2383", name: "Kodak Vision 2383" },
  { id: "kodak_2393", name: "Kodak Vision Premier 2393" },
  { id: "fujifilm_crystal_archive_typeii", name: "Fujifilm Crystal Archive Type II" },
];

export function filmSwatch(id: string): string {
  return FILM[id] ?? hashed(id);
}

export function paperSwatch(id: string): string {
  return PAPER[id] ?? hashed(id);
}

function hashed(id: string): string {
  let hash = 0;
  for (const char of id) {
    hash = (hash * 33 + char.charCodeAt(0)) >>> 0;
  }
  const warm = 18 + (hash % 36);
  const cool = 168 + ((hash >> 8) % 40);
  const deep = 40 + ((hash >> 16) % 30);
  return `linear-gradient(128deg, hsl(${warm} 46% 68%), hsl(${deep} 32% 46%) 52%, hsl(${cool} 28% 42%))`;
}
