/* SpektraFilm Windows edition — GPLv3. See LICENSE in the repository root.
   Original color studies for the stock strip. Not measured science, and not
   artwork from any other film application. */

const FILM: Record<string, string> = {
  kodak_portra_160: "linear-gradient(128deg, #f4d8c6 0%, #e7b39a 46%, #7eb7be 100%)",
  kodak_portra_400: "linear-gradient(128deg, #f6d0b2 0%, #e39a84 48%, #5f9aa6 100%)",
  kodak_portra_800: "linear-gradient(128deg, #efc0a0 0%, #d48472 50%, #4d828c 100%)",
  kodak_portra_800_push1: "linear-gradient(128deg, #e8ae8c 0%, #c4685e 52%, #3f707a 100%)",
  kodak_portra_800_push2: "linear-gradient(128deg, #d69474 0%, #b4524c 54%, #345860 100%)",
  kodak_gold_200: "linear-gradient(152deg, #f7e3a4, #e2a056 58%, #c26446)",
  kodak_ultramax_400: "linear-gradient(146deg, #f0c888, #d67e56 52%, #8a5644)",
  kodak_ektar_100: "linear-gradient(138deg, #f3c6ae, #de6c54 38%, #3d7a62 74%, #24566e)",
  kodak_ektachrome_100: "linear-gradient(136deg, #d5e3ea, #7eb0c8 46%, #3d6e58)",
  kodak_kodachrome_64: "linear-gradient(150deg, #e8c8a2, #c45444 44%, #2f6a52 82%)",
  kodak_vision3_50d: "linear-gradient(136deg, #efe6d2, #d8b488 42%, #6a8ea4)",
  kodak_vision3_250d: "linear-gradient(136deg, #ead6b8, #c99664 46%, #4e7490)",
  kodak_vision3_200t: "linear-gradient(136deg, #d6c6e6, #8876b4 50%, #3a5878)",
  kodak_vision3_500t: "linear-gradient(136deg, #c8b4d8, #6c5894 52%, #2c4460)",
  kodak_verita_200d: "linear-gradient(142deg, #f0dcc2, #d6a674 52%, #7a9aaa)",
  fujifilm_pro_400h: "linear-gradient(146deg, #dceee6, #8ec4b4 44%, #e8c4c8)",
  fujifilm_provia_100f: "linear-gradient(140deg, #e4f0ea, #5a9a88 50%, #3a6a88)",
  fujifilm_velvia_100: "linear-gradient(146deg, #f2e0c8, #d05048 34%, #1f7a58 70%, #1a4a78)",
  fujifilm_c200: "linear-gradient(152deg, #f4e0b0, #e0a060 56%, #a86848)",
  fujifilm_xtra_400: "linear-gradient(152deg, #f6d898, #d88848 54%, #8a5040)",
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
