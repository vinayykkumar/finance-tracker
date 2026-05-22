/**
 * Glossary slice (062): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "062" as const;
export const termEn = "principal payment" as const;
export function describeTerm(): string {
  return termEn;
}
