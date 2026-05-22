/**
 * Glossary slice (032): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "032" as const;
export const termEn = "fixed expense" as const;
export function describeTerm(): string {
  return termEn;
}
