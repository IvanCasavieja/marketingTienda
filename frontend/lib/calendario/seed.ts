// Generado por scripts/importar-excel.py — no editar a mano.
//   retail    <- 'Calendario espacios digitales y datos de campaña.xlsx'
//   comercial <- 'CALENDARIO 2025 Y 2026 TI.xlsx'

import type { SeedMes } from './tipos'

/** Cambia cada vez que se reimportan los Excel. */
export const SEED_VERSION = '35daa28a044e'

export const SEED: Record<string, SeedMes> = {
  '2026-09': {
    dias: 30,
    dow: {"1": "M", "2": "M", "3": "J", "4": "V", "5": "S", "6": "D", "7": "L", "8": "M", "9": "M", "10": "J", "11": "V", "12": "S", "13": "D", "14": "L", "15": "M", "16": "M", "17": "J", "18": "V", "19": "S", "20": "D", "21": "L", "22": "M", "23": "M", "24": "J", "25": "V", "26": "S", "27": "D", "28": "L", "29": "M", "30": "M"},
    comercial: [
      { nombre: "MEGA EVENTO", filas: [
        [{ nombre: "MRP 8 PAG", desde: 1, hasta: 6, color: null }, { nombre: "EXTENSION MRP (fisico y web)", desde: 7, hasta: 7, color: "#808080" }],
      ] },
      { nombre: "Mailing GRAL", filas: [
        [{ nombre: "Mailing Fiesta de Italia 20% en todo tematico + 10% scotia ccc - 48 pag", desde: 9, hasta: 23, color: "#8EA9DB" }],
        [{ nombre: "PRECIAZOS +15% CCC 4 PAG -POSADAS, UNION, PROPIOS, LAGOMAR, ATLANTIDA, ATLANTICO Y CORDÓN (no web)", desde: 8, hasta: 30, color: "#FF0000" }],
      ] },
      { nombre: "Sin mailing", filas: [
        [{ nombre: "Expo Rural del Prado 15% CCC PRODUCTOS GB", desde: 11, hasta: 20, color: "#FFC000" }, { nombre: "(OI) ELECTRO SALE", desde: 25, hasta: 30, color: "#375623" }],
        [{ nombre: "ESPECIAL ROMPE PRECIOS CUIDADO PERSONAL +15% SCOTIA", desde: 15, hasta: 22, color: null }, { nombre: "ESPECIAL ROMPE PRECIOS LIMPIEZA + 15% SCOTIA CCC", desde: 23, hasta: 30, color: null }],
        [{ nombre: "ESPECIAL ROMPE PRECIOS CONGELADOS + 15% SCOTIA CCC", desde: 23, hasta: 30, color: "#FFFF00" }],
        [{ nombre: "(OI) ESPECIAL DEPORTES & TIEMPO LIBRE", desde: 18, hasta: 30, color: "#7030A0" }],
      ] },
      { nombre: "Mailing NF", filas: [
        [],
      ] },
      { nombre: "Evento NF", filas: [
        [{ nombre: "CONTAINER", desde: 18, hasta: 23, color: "#33FF52" }, { nombre: "CONTAINER FAKE", desde: 24, hasta: 27, color: "#33FF52" }],
      ] },
      { nombre: "Ecommerce TI", filas: [
        [{ nombre: "CIBER OFERTAS", desde: 8, hasta: 13, color: "#FFFF00" }, { nombre: "Fiestas Online Scotia ccc Hasta 15% seleccionados", desde: 14, hasta: 21, color: "#FF00FF" }, { nombre: "CIBER OFERTAS", desde: 22, hasta: 30, color: "#FFFF00" }],
        [{ nombre: "20% OFF SUSHI TI EX", desde: 5, hasta: 5, color: null }, { nombre: "20% OFF SUSHI TI EX", desde: 12, hasta: 12, color: null }, { nombre: "20% OFF SUSHI TI EX", desde: 19, hasta: 19, color: null }, { nombre: "20% OFF SUSHI TI EX", desde: 26, hasta: 26, color: null }],
      ] },
      { nombre: "ACTIVIDADES TACTICAS", filas: [
        [{ nombre: "FyV 30%", desde: 1, hasta: 1, color: "#00B050" }, { nombre: "P&P 30%", desde: 2, hasta: 2, color: "#00B0F0" }, { nombre: "F & P 30%", desde: 3, hasta: 3, color: null }, { nombre: "P & E 30%", desde: 4, hasta: 4, color: null }, { nombre: "P&C 30%", desde: 7, hasta: 7, color: "#FF0066" }, { nombre: "FyV 30%", desde: 8, hasta: 8, color: "#00B050" }, { nombre: "P&P 30%", desde: 9, hasta: 9, color: "#00B0F0" }, { nombre: "F & P 30%", desde: 10, hasta: 10, color: null }, { nombre: "P & E 30%", desde: 11, hasta: 11, color: null }, { nombre: "P&C 30%", desde: 14, hasta: 14, color: "#FF0066" }, { nombre: "FyV 30%", desde: 15, hasta: 15, color: "#00B050" }, { nombre: "P&P 30%", desde: 16, hasta: 16, color: "#00B0F0" }, { nombre: "F & P 30%", desde: 17, hasta: 17, color: null }, { nombre: "P & E 30%", desde: 18, hasta: 18, color: null }, { nombre: "P&C 30%", desde: 21, hasta: 21, color: "#FF0066" }, { nombre: "FyV 30%", desde: 22, hasta: 22, color: "#00B050" }, { nombre: "P&P 30%", desde: 23, hasta: 23, color: "#00B0F0" }, { nombre: "F & P 30%", desde: 24, hasta: 24, color: null }, { nombre: "P & E 30%", desde: 25, hasta: 25, color: null }, { nombre: "P&C 30%", desde: 28, hasta: 28, color: "#FF0066" }, { nombre: "FyV 30%", desde: 29, hasta: 29, color: "#00B050" }, { nombre: "P&P 30%", desde: 30, hasta: 30, color: "#00B0F0" }],
        [{ nombre: "RPFDS", desde: 10, hasta: 13, color: "#FF0000" }, { nombre: "RPFDS (4)", desde: 17, hasta: 20, color: "#FF0000" }, { nombre: "RPFDS 4 PAG (CARNES )", desde: 24, hasta: 27, color: "#FF0000" }],
      ] },
      { nombre: "TIENDA FARMA", filas: [
        [{ nombre: "TIENDA FARMA PRIMAVERA", desde: 9, hasta: 30, color: null }],
      ] },
      { nombre: "Seasonal 1", filas: [
        [{ nombre: "MRP 8 PAG", desde: 1, hasta: 6, color: null }, { nombre: "Mailing Fiesta de Italia 25% en todo tematico 48 pag", desde: 9, hasta: 23, color: "#8EA9DB" }],
      ] },
      { nombre: "Seasonal 2 CENTRAL/ PROPIOS / PUNTA SHOPPING", filas: [
        [{ nombre: "MRP 8 PAG", desde: 1, hasta: 6, color: null }],
      ] },
      { nombre: "Carpas", filas: [
        [],
      ] },
      { nombre: "Pasillos Laterales", filas: [
        [],
      ] },
      { nombre: "Galería y/o Estacionamiento", filas: [
        [],
      ] },
    ],
    retail: [
      { nombre: "HOME SLIDER (Retail Media)", grupo: "eComm", filas: [
        [{ nombre: "MILKA - Mondelez", desde: 1, hasta: 7, color: "#D9D2E9" }, { nombre: "PepsiCo - Doritos Pizza", desde: 11, hasta: 17, color: "#FFF2CC" }, { nombre: "Copacabana - Nestlé", desde: 18, hasta: 27, color: "#C9DAF8" }, { nombre: "Conaprole", desde: 28, hasta: 30, color: "#93C47D" }],
        [{ nombre: "DOVE DREAM", desde: 1, hasta: 8, color: "#B6D7A8" }, { nombre: "SCJ - GLADE Home Fragance", desde: 10, hasta: 15, color: "#D0E0E3" }, { nombre: "OREO", desde: 16, hasta: 22, color: "#FFF2CC" }, { nombre: "Conaprole", desde: 23, hasta: 25, color: "#93C47D" }, { nombre: "Nestle - NDG", desde: 26, hasta: 30, color: "#D9D9D9" }],
        [{ nombre: "SCJ - GLADE Home Fragance", desde: 4, hasta: 9, color: "#D0E0E3" }, { nombre: "Glade - Aussie", desde: 11, hasta: 18, color: "#D0E0E3" }, { nombre: "COLPAL", desde: 19, hasta: 23, color: "#EA9999" }, { nombre: "Block Friday", desde: 24, hasta: 27, color: "#E6B8AF" }],
      ] },
      { nombre: "HOME SLIDER (Comercial con marcas)", grupo: "eComm", filas: [
        [{ nombre: "COLPAL", desde: 8, hasta: 10, color: "#EA9999" }],
        [{ nombre: "Conaprole", desde: 8, hasta: 13, color: "#C9DAF8" }, { nombre: "Conaprole", desde: 20, hasta: 30, color: "#C9DAF8" }],
      ] },
      { nombre: "FINO FIJO HOME", grupo: "eComm", filas: [
        [{ nombre: "Glade - Aussie", desde: 19, hasta: 24, color: "#D0E0E3" }],
        [{ nombre: "Mondelez - Brand Shelf Home MILKA", desde: 11, hasta: 17, color: "#D9D2E9" }, { nombre: "Nestle - NDG - Brand Shelf Home", desde: 23, hasta: 29, color: "#D9D9D9" }],
        [{ nombre: "SCJ - GLADE (AGO)", desde: 1, hasta: 2, color: "#B7B7B7" }, { nombre: "Brand Shelf Home - SCJ Ofertas Mensuales", desde: 7, hasta: 12, color: "#D9EAD3" }, { nombre: "SCJ - GLADE Home Fragance", desde: 13, hasta: 18, color: "#D0E0E3" }, { nombre: "SCJ - GLADE Home Fragance", desde: 19, hasta: 24, color: "#B7B7B7" }],
      ] },
      { nombre: "CARRUSEL", grupo: "eComm", filas: [
        [{ nombre: "Carrusel para Brand Shelf Home - SCJ Ofertas Mensuales", desde: 7, hasta: 12, color: "#D9EAD3" }, { nombre: "Nestle - NDG - Brand Shelf Home - Carrusel", desde: 23, hasta: 29, color: "#D9D9D9" }],
        [{ nombre: "Mondelez - Brand Shelf Home MILKA", desde: 11, hasta: 17, color: "#D9D2E9" }],
      ] },
      { nombre: "Banners Dobles", grupo: "eComm", filas: [
        [{ nombre: "La Especialista", desde: 9, hasta: 15, color: "#F9CB9C" }],
        [{ nombre: "Jaspe", desde: 9, hasta: 15, color: "#EAD1DC" }],
      ] },
      { nombre: "Banners Cuadruples", grupo: "eComm", filas: [
        [{ nombre: "Ofertas Tuyas, Rumba, Oreo, MIlka,", desde: 2, hasta: 2, color: null }],
      ] },
      { nombre: "Banner Categoria", grupo: "eComm", filas: [
        [{ nombre: "Limpieza - SCJ - Glade Aussie", desde: 15, hasta: 30, color: "#D9EAD3" }],
        [{ nombre: "Mondelez - Golosinas y Chocolates", desde: 1, hasta: 30, color: "#D9D2E9" }],
        [{ nombre: "COLPAL - Higiene Bucal", desde: 7, hasta: 13, color: "#EA9999" }, { nombre: "COLPAL - Higiene Bucal (Limpieza interdental)", desde: 16, hasta: 22, color: "#EA9999" }],
        [{ nombre: "Tolaiitas Humedas - Softys", desde: 4, hasta: 10, color: "#D9D9D9" }],
        [{ nombre: "Limpieza - SCJ - Glade Home Fragance", desde: 1, hasta: 30, color: null }],
      ] },
      { nombre: "Category Brand Tree", grupo: "eComm", filas: [
        [{ nombre: "Mondelez - Almacen", desde: 1, hasta: 30, color: "#D9D2E9" }],
        [{ nombre: "Dove cream - Cuidado capilar", desde: 1, hasta: 30, color: "#93C47D" }],
      ] },
      { nombre: "Banner check out", grupo: "eComm", filas: [
        [{ nombre: "Milka Promo", desde: 4, hasta: 6, color: null }, { nombre: "Oreo Gold", desde: 7, hasta: 9, color: null }, { nombre: "Pepsico - Doritos Pizza", desde: 10, hasta: 12, color: null }, { nombre: "Café Nestlé - Copacabana", desde: 16, hasta: 18, color: null }, { nombre: "Glade Aussie", desde: 19, hasta: 21, color: "#D9D2E9" }, { nombre: "Cofler Block", desde: 24, hasta: 27, color: "#F4CCCC" }, { nombre: "Copacabana", desde: 28, hasta: 30, color: "#9FC5E8" }],
      ] },
      { nombre: "Banner check out (Express)", grupo: "Express", filas: [
        [],
        [{ nombre: "Milka Promo", desde: 4, hasta: 6, color: null }, { nombre: "Oreo Gold", desde: 7, hasta: 9, color: null }, { nombre: "Pepsico - Doritos Pizza", desde: 10, hasta: 12, color: null }, { nombre: "Café Nestlé - Copacabana", desde: 16, hasta: 18, color: null }, { nombre: "Glade Aussie", desde: 19, hasta: 21, color: "#D9D2E9" }, { nombre: "Cofler Block", desde: 24, hasta: 27, color: "#F4CCCC" }, { nombre: "Copacabana", desde: 28, hasta: 30, color: "#9FC5E8" }],
        [],
        [],
        [],
        [{ nombre: "Campañas a tener en cuenta + CAMPAÑAS ALWAYS ON", desde: 6, hasta: 8, color: "#D0E0E3" }, { nombre: "MILKA", desde: 9, hasta: 9, color: "#D9EAD3" }],
        [{ nombre: "OREO", desde: 9, hasta: 9, color: "#D9EAD3" }],
        [{ nombre: "SCJ", desde: 9, hasta: 9, color: "#D9EAD3" }, { nombre: "GLADE Home Fragance", desde: 10, hasta: 10, color: "#D9EAD3" }],
        [{ nombre: "SCJ", desde: 9, hasta: 9, color: "#D9EAD3" }, { nombre: "Glade Aussie", desde: 10, hasta: 10, color: "#D9EAD3" }],
        [{ nombre: "SCJ", desde: 9, hasta: 9, color: "#D9EAD3" }, { nombre: "Ofertas Mensuales", desde: 10, hasta: 10, color: "#D9EAD3" }],
        [{ nombre: "DOVE DREAM", desde: 9, hasta: 9, color: "#D9EAD3" }],
        [{ nombre: "NESTLÉ", desde: 9, hasta: 9, color: "#D9EAD3" }, { nombre: "Copacabana", desde: 10, hasta: 10, color: "#D9EAD3" }],
        [{ nombre: "NESTLÉ", desde: 9, hasta: 9, color: "#D9EAD3" }, { nombre: "Kit Molidos", desde: 10, hasta: 10, color: "#D9EAD3" }],
        [{ nombre: "NESTLÉ", desde: 9, hasta: 9, color: "#D9EAD3" }, { nombre: "Kit NDG", desde: 10, hasta: 10, color: "#D9EAD3" }],
      ] },
    ],
  },
  '2026-10': {
    dias: 31,
    dow: {"1": "J", "2": "V", "3": "S", "4": "D", "5": "L", "6": "M", "7": "M", "8": "J", "9": "V", "10": "S", "11": "D", "12": "L", "13": "M", "14": "M", "15": "J", "16": "V", "17": "S", "18": "D", "19": "L", "20": "M", "21": "M", "22": "J", "23": "V", "24": "S", "25": "D", "26": "L", "27": "M", "28": "M", "29": "J", "30": "V", "31": "S"},
    comercial: [
      { nombre: "MEGA EVENTO", filas: [
        [{ nombre: "Mailing Fiesta de Alemania 20% + 10 % CCC", desde: 8, hasta: 18, color: "#BF8F00" }, { nombre: "FIESTA DE ESPAÑA 20% + 10% CCC", desde: 29, hasta: 31, color: "#FF0000" }],
      ] },
      { nombre: "Mailing GRAL", filas: [
        [{ nombre: "TiendaChecks 28 pag", desde: 2, hasta: 7, color: "#92D050" }, { nombre: "TiendaChecks REDENCIÓN", desde: 8, hasta: 11, color: null }, { nombre: "Mailing Marca Propia + Limpieza + No Tematicos y CP 24 pág", desde: 12, hasta: 18, color: null }, { nombre: "COLECCIONABLE", desde: 19, hasta: 28, color: null }],
      ] },
      { nombre: "Especiales", filas: [
        [{ nombre: "ESPECIAL ROMPE PRECIOS CONGELADOS + 15% SCOTIA CCC", desde: 12, hasta: 19, color: null }, { nombre: "ESPECIAL ROMPE PRECIOS CUIDADO PERSONAL +15% SCOTIA", desde: 20, hasta: 27, color: null }],
      ] },
      { nombre: "Sin mailing", filas: [
        [{ nombre: "ELECTRO SALE OI", desde: 1, hasta: 7, color: null }, { nombre: "HALLOWEEN - (D) 4 pag", desde: 27, hasta: 31, color: null }],
      ] },
      { nombre: "Mailing NF", filas: [
        [{ nombre: "AMY Coleccion Primavera-Verano- 25% CCC", desde: 14, hasta: 26, color: "#FF0066" }],
      ] },
      { nombre: "Evento NF", filas: [
        [],
      ] },
      { nombre: "Ecommerce TI", filas: [
        [{ nombre: "CIBER OFERTAS", desde: 15, hasta: 20, color: "#FFFF00" }, { nombre: "CIBER OFERTAS", desde: 23, hasta: 30, color: "#FFFF00" }],
        [{ nombre: "20% OFF SUSHI TI EX", desde: 10, hasta: 10, color: null }, { nombre: "20% OFF SUSHI TI EX", desde: 17, hasta: 17, color: null }, { nombre: "20% OFF SUSHI TI EX", desde: 24, hasta: 24, color: null }, { nombre: "20% OFF SUSHI TI EX", desde: 31, hasta: 31, color: null }],
      ] },
      { nombre: "ACTIVIDADES TACTICAS", filas: [
        [{ nombre: "F & P 30%", desde: 1, hasta: 1, color: null }, { nombre: "P & E 30%", desde: 2, hasta: 2, color: null }, { nombre: "P&C 30%", desde: 5, hasta: 5, color: "#FF0066" }, { nombre: "FyV 30%", desde: 6, hasta: 6, color: "#00B050" }, { nombre: "P&P 30%", desde: 7, hasta: 7, color: "#00B0F0" }, { nombre: "F & P 30%", desde: 8, hasta: 8, color: null }, { nombre: "P & E 30%", desde: 9, hasta: 9, color: null }, { nombre: "P&C 30%", desde: 12, hasta: 12, color: "#FF0066" }, { nombre: "FyV 30%", desde: 13, hasta: 13, color: "#00B050" }, { nombre: "P&P 30%", desde: 14, hasta: 14, color: "#00B0F0" }, { nombre: "F & P 30%", desde: 15, hasta: 15, color: null }, { nombre: "P & E 30%", desde: 16, hasta: 16, color: null }, { nombre: "P&C 30%", desde: 19, hasta: 19, color: "#FF0066" }, { nombre: "FyV 30%", desde: 20, hasta: 20, color: "#00B050" }, { nombre: "P&P 30%", desde: 21, hasta: 21, color: "#00B0F0" }, { nombre: "F & P 30%", desde: 22, hasta: 22, color: null }, { nombre: "P & E 30%", desde: 23, hasta: 23, color: null }, { nombre: "P&C 30%", desde: 26, hasta: 26, color: "#FF0066" }, { nombre: "FyV 30%", desde: 27, hasta: 27, color: "#00B050" }, { nombre: "P&P 30%", desde: 28, hasta: 28, color: "#00B0F0" }, { nombre: "F & P 30%", desde: 29, hasta: 29, color: null }, { nombre: "P & E 30%", desde: 30, hasta: 30, color: null }],
        [{ nombre: "RPFDS", desde: 15, hasta: 18, color: "#FF0000" }, { nombre: "RPFDS", desde: 22, hasta: 25, color: "#FF0000" }, { nombre: "RPFDS", desde: 29, hasta: 31, color: "#FF0000" }],
      ] },
      { nombre: "Seasonal 1", filas: [
        [],
      ] },
      { nombre: "Seasonal 2 CENTRAL/ PROPIOS / PUNTA SHOPPING", filas: [
        [],
      ] },
      { nombre: "Carpas", filas: [
        [],
      ] },
      { nombre: "Pasillos Laterales", filas: [
        [],
      ] },
      { nombre: "Galería y/o Estacionamiento", filas: [
        [],
      ] },
    ],
    retail: [
      { nombre: "HOME SLIDER (Retail Media)", grupo: "eComm", filas: [
        [{ nombre: "Conaprole", desde: 1, hasta: 2, color: "#93C47D" }],
      ] },
      { nombre: "FINO FIJO HOME", grupo: "eComm", filas: [
        [],
        [],
        [{ nombre: "KIT MOLIDOS - Nestlé - Brand Shelf Home", desde: 3, hasta: 9, color: "#A64D79" }],
      ] },
      { nombre: "CARRUSEL", grupo: "eComm", filas: [
        [{ nombre: "KIT MOLIDOS - Nestlé - Brand Shelf Home Carrusel", desde: 3, hasta: 9, color: "#A64D79" }],
      ] },
      { nombre: "Category Brand Tree", grupo: "eComm", filas: [
        [],
        [{ nombre: "DOVE CREAM - CUIDADO CAPILAR", desde: 1, hasta: 31, color: "#93C47D" }],
      ] },
      { nombre: "Banner check out", grupo: "eComm", filas: [
        [],
        [],
        [],
        [],
        [],
        [{ nombre: "A contemplar:", desde: 3, hasta: 3, color: null }],
        [{ nombre: "- Conaprole OCT (15 días)", desde: 3, hasta: 3, color: null }],
        [{ nombre: "- Jaspe (doble)", desde: 3, hasta: 3, color: null }],
      ] },
    ],
  },
}
