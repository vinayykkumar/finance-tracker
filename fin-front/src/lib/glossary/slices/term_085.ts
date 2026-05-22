/**
 * Glossary slice (085): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "085" as const;
export const termEn = "balance transfer" as const;
export function describeTerm(): string {
  return termEn;
}
