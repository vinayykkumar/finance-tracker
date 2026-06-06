/**
 * Glossary slice (079): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "079" as const;
export const termEn = "wire transfer" as const;
export function describeTerm(): string {
  return termEn;
}
