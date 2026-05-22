/**
 * Glossary slice (055): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "055" as const;
export const termEn = "mortgage principal" as const;
export function describeTerm(): string {
  return termEn;
}
