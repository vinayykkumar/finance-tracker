/**
 * Glossary slice (013): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "013" as const;
export const termEn = "cash flow" as const;
export function describeTerm(): string {
  return termEn;
}
