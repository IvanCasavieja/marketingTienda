export function fNum(n: number): string {
  return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

export function fMoney(n: number): string {
  return "$" + fNum(n);
}
