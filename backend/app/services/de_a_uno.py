"""Lo pesado en memoria, de a uno en todo el proceso: un PDF abierto con
PyMuPDF o una imagen grande decodificada.

PyMuPDF no se puede usar desde dos hilos a la vez (su documentación avisa
que puede tirar abajo el proceso), y dos imágenes grandes juntas en los 512
MB del servidor son demasiado. Por eso todo el que abre un PDF con PyMuPDF
toma `DE_A_UNO` mientras lo usa, y lo suelta después de vaciar su depósito
(`TOOLS.store_shrink`):

- app/services/materiales.py: la entrega, en el pedido
  (`imagenes_para_la_ronda`), y la IA, en segundo plano (`extraer_del_zip`),
  cada una desde su hilo. Ahí cubre también las imágenes grandes.
- app/services/rrss/imagenes.py: la validación de RRSS, al dibujar las
  páginas del mailing (`_render`).

Hasta la revisión del 19/11/2026 el candado vivía en materiales.py y la
validación de RRSS no lo tomaba: un mailing y el PDF de una entrega podían
usar PyMuPDF a la vez. Vive acá para que lo compartan.

Reentrante (RLock), por si una función que lo tiene llama a otra que lo pide:
el mismo hilo no se traba consigo mismo. Se toma siempre desde un hilo
(asyncio.to_thread), nunca en el loop del servidor: esperarlo ahí frenaría
todos los pedidos.
"""
import threading

DE_A_UNO = threading.RLock()
