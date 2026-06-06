/**
 * Glossary slice (012): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "012" as const;
export const termEn = "capital gain" as const;
export function describeTerm(): string {
  return termEn;
}
