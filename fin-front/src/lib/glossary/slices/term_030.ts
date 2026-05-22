/**
 * Glossary slice (030): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "030" as const;
export const termEn = "FDIC insurance" as const;
export function describeTerm(): string {
  return termEn;
}
