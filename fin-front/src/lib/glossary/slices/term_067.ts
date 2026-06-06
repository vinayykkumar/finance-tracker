/**
 * Glossary slice (067): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "067" as const;
export const termEn = "routing number" as const;
export function describeTerm(): string {
  return termEn;
}
