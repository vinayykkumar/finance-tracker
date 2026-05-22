/**
 * Glossary slice (018): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "018" as const;
export const termEn = "compound interest" as const;
export function describeTerm(): string {
  return termEn;
}
