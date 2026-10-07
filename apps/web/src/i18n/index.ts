import en, { type Dictionary } from "./en";
import id from "./id";

export type Locale = "en" | "id";

export const dictionaries: Record<Locale, Dictionary> = { en, id };

export function getDictionary(locale: Locale): Dictionary {
  return dictionaries[locale];
}

export type { Dictionary };
