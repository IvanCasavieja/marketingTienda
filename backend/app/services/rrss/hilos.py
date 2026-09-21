"""El trabajo de imágenes (decodificar una placa de 2250 px, achicarla,
codificarla, dibujar la grilla, recortar) es CPU puro y SINCRÓNICO. Correrlo
directo dentro de una corrutina congela el event loop entero mientras dura: el
servidor corre un solo proceso de uvicorn, así que se congela para todos --
incluido /health, que Render consulta para saber si el servicio está vivo -- y
en una instancia chica cada ráfaga dura segundos, no milisegundos.

`en_hilo` lo manda a un hilo (PIL suelta el GIL en decodificar/achicar/codificar)
y además deja pasar UN trabajo de estos a la vez: cada uno decodifica una imagen
entera (15 a 30 MB) y varios a la vez, en una instancia de 512 MB, es lo que
mata el proceso por falta de memoria. Las llamadas a la IA, que son la parte
lenta, siguen corriendo todas en paralelo: esto solo ordena el trabajo de CPU.
"""
import asyncio

_CPU = asyncio.Semaphore(1)


async def en_hilo(funcion, *args, **kwargs):
    async with _CPU:
        return await asyncio.to_thread(funcion, *args, **kwargs)
