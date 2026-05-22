/**
 * Glossary slice (005): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "005" as const;
export const termEn = "available balance" as const;
export function describeTerm(): string {
  return termEn;
}
