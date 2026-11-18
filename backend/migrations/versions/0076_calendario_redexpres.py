"""el calendario de Redexpres, cargado de su Excel (PAC 2026)

Pedido de Ivan (18/11/2026): "dejé el calendario de Redexpres en descargas,
lo ideal es que el calendario de Redex sea idéntico a esto". Son las acciones
de las hojas de enero a diciembre de 2026 de "PAC 2026 Tareas.xlsx", con sus
fechas, su fila (la categoría, ver BANDAS_REDEXPRES en frontend/lib/mundos.ts)
y su color. Se armaron así:

- una acción que sigue de un mes al otro (en la misma fila y con el mismo
  nombre, sin nombrar meses distintos) es UNA sola;
- las barras pintadas sin texto de "Super FDS" y "BOMBAS" llevan el nombre
  de su fila;
- la hoja "ENERO 27" no se cargó: es una copia de enero 2026 (mismos ID de
  mailing).

Es aditiva y se puede correr de nuevo: no crea una acción si ya hay otra de
Redexpres con el mismo nombre y el mismo día de arranque, y no toca nada que
ya esté. La hoja "Valen" (las tareas de Valentina en cada acción) no se carga:
primero se validan con ella.

Revision ID: 0076
Revises: 0075
Create Date: 2026-11-18
"""
from datetime import date

import sqlalchemy as sa
from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None

MUNDO = "redexpres"

# (id, fila, renglón, nombre, color, desde, hasta)
ACCIONES = [
    ('br-rx-ee1384200359', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-01-01', '2026-01-04'),
    ('br-rx-6a6b6c77d3a2', 'ESPECIAL - CM', 0, 'ESPECIAL JUGUETES (5) ELECTRO (2) 8 PAG', '#ffc000', '2026-01-01', '2026-01-06'),
    ('br-rx-f6724754b3c4', 'MAILING - 16 PAG EL PAIS', 0, 'MAILING ENERO - 16 pág (SOLO X 25 + MP + ESPECIAL BEBIDAS) / ID 11287', '#92d050', '2026-01-02', '2026-01-25'),
    ('br-rx-4bf8cc8fefc3', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-01-08', '2026-01-11'),
    ('br-rx-031040c50bcb', 'BOMBAS', 0, 'NO CARNE', '#c65911', '2026-01-15', '2026-01-18'),
    ('br-rx-e29ec5e9f507', 'BOMBAS', 0, 'NO CARNE', '#c65911', '2026-01-22', '2026-01-25'),
    ('br-rx-765c51e5e446', 'MAILING - 16 PAG EL PAIS', 0, 'MAILING FEBRERO - 16 pág (SOLO X 25 + MP) ID 11371', '#46b1e1', '2026-01-26', '2026-02-22'),
    ('br-rx-e43ec0d2b19c', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-01-29', '2026-01-29'),
    ('br-rx-74a617d2e5e8', 'ESPECIAL - CM', 0, 'Preciazos - 2 pág (ID 11711)', '#ffc000', '2026-01-29', '2026-03-01'),
    ('br-rx-55d077fc5e8c', 'BOMBAS', 0, 'Bombas', '#c65911', '2026-02-05', '2026-02-08'),
    ('br-rx-92a04f74e8a8', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-02-05', '2026-02-08'),
    ('br-rx-033324d71f01', 'ESPECIAL - CM', 1, 'Especial cervezas', '#ffc000', '2026-02-06', '2026-02-22'),
    ('br-rx-b0901c4996ae', 'BOMBAS', 0, 'Bombas', '#c65911', '2026-02-12', '2026-02-15'),
    ('br-rx-e66eab63daa8', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-02-12', '2026-02-15'),
    ('br-rx-840959df5a33', 'ESPECIAL - CM', 2, 'ESPECIAL VUELTA A CLASES - 8 PAG', '#ffff00', '2026-02-16', '2026-03-15'),
    ('br-rx-c09ddb88a539', 'BOMBAS', 0, 'Bombas', '#c65911', '2026-02-19', '2026-02-22'),
    ('br-rx-594a5586b55f', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-02-19', '2026-02-22'),
    ('br-rx-b929f93b02a9', 'MAILING - 40 PAG EL PAIS', 0, 'ESPECIAL El Estadio en Casa (SORTEO Y AVISOS) MAILING MARZO - 40 PAG (id 11624)', '#00b0f0', '2026-02-23', '2026-03-29'),
    ('br-rx-fa551c44c448', 'TÁCTICO (x LOCAL) CM', 0, 'Mundo Hogar MARZO - 4 Pág (ID 11715)', '#ffff00', '2026-02-23', '2026-03-29'),
    ('br-rx-a1c4fdae5fbe', 'BOMBAS', 0, 'Bombas', '#c04f15', '2026-02-26', '2026-02-28'),
    ('br-rx-3644188b9167', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-03-05', '2026-03-08'),
    ('br-rx-aba343ca749d', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-03-05', '2026-03-08'),
    ('br-rx-aa2964fbac29', 'ESPECIAL - CM', 0, 'Preciazos - 2 pág', '#ffc000', '2026-03-11', '2026-04-30'),
    ('br-rx-bdac9d2d39c0', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-03-12', '2026-03-15'),
    ('br-rx-0439c5d65f30', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-03-12', '2026-03-15'),
    ('br-rx-9a4830576486', 'BOMBAS', 0, 'NO CARNE', '#c65911', '2026-03-19', '2026-03-22'),
    ('br-rx-2d2d7ec9bcc0', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-03-19', '2026-03-22'),
    ('br-rx-48e96ac0287d', 'MAILING - 40 PAG EL PAIS', 1, 'ESPECIAL PASCUAS - 8 PAG', '#a02b93', '2026-03-24', '2026-03-31'),
    ('br-rx-50099b1eb841', 'BOMBAS', 0, 'NO CARNE', '#c65911', '2026-03-26', '2026-03-29'),
    ('br-rx-8cecf54e6aa1', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-03-26', '2026-03-29'),
    ('br-rx-f0406bc62362', 'TÁCTICO (x LOCAL) CM', 0, 'Mundo Hogar ABRIL - 4 Pág ( ID 11716)', '#ffc000', '2026-03-30', '2026-04-27'),
    ('br-rx-af9f9ad60035', 'ESPECIAL - CM', 0, 'ESPECIAL PASCUAS - 8 PAG', '#a02b93', '2026-04-01', '2026-04-05'),
    ('br-rx-1979d15cdc07', 'MAILING - 16 PAG EL PAIS', 0, 'MAILING ABRIL - 16 pág (SOLO X 25 + MP)', '#ffff00', '2026-04-01', '2026-04-27'),
    ('br-rx-7c92060ec0a0', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-04-02', '2026-04-05'),
    ('br-rx-315b7c09b6e6', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-04-02', '2026-04-05'),
    ('br-rx-1a7db5e7e53e', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-04-09', '2026-04-12'),
    ('br-rx-1bf800b17656', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-04-09', '2026-04-12'),
    ('br-rx-33f58e4310fb', 'BOMBAS', 0, 'NO CARNE', '#c65911', '2026-04-16', '2026-04-19'),
    ('br-rx-dc48d9002d88', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-04-16', '2026-04-19'),
    ('br-rx-a699f571fb0b', 'ESPECIAL - CM', 0, 'ESPECIAL PARRILLA -4 PAG', '#a02b93', '2026-04-23', '2026-05-03'),
    ('br-rx-c2dc877605e7', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-04-23', '2026-04-26'),
    ('br-rx-79c78ae2d35c', 'MAILING - 16 PAG EL PAIS', 0, 'MAILING MAYO - 16 pág (SOLO X 25 + MP)', '#4ea72e', '2026-04-28', '2026-05-27'),
    ('br-rx-de023177db4e', 'TÁCTICO (x LOCAL) CM', 0, 'Mundo Hogar MAYO- 4 Pág', '#ffff00', '2026-04-28', '2026-05-27'),
    ('br-rx-9df3d2a87d90', 'ESPECIAL - CM', 1, 'Preciazos mayo (ID 12240)', '#ffc000', '2026-05-02', '2026-05-31'),
    ('br-rx-5971024bbba8', 'ESPECIAL - CM', 0, 'DDM 4 PAG', '#ffc000', '2026-05-04', '2026-05-10'),
    ('br-rx-c4f4a8197785', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-05-07', '2026-05-10'),
    ('br-rx-fc0c3bcef8eb', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-05-07', '2026-05-10'),
    ('br-rx-440361f13141', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-05-14', '2026-05-17'),
    ('br-rx-6f1bb274d034', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-05-14', '2026-05-17'),
    ('br-rx-189569a14561', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-05-21', '2026-05-24'),
    ('br-rx-47bbb5e60ed6', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-05-21', '2026-05-24'),
    ('br-rx-a6da93401a66', 'ESPECIAL - CM', 0, 'MAILING BLACK MUNDIAL JUNIO - 16 pág (tv, audio, copetin, cerveza + MP + MUNDIAL)', '#ffc000', '2026-05-28', '2026-06-03'),
    ('br-rx-46eb5df08509', 'ESPECIAL - CM', 1, 'Preciazos junio', '#ffc000', '2026-06-01', '2026-06-30'),
    ('br-rx-0fa8d098a09e', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-06-04', '2026-06-07'),
    ('br-rx-e4a85d16bd2d', 'ESPECIAL - CM', 0, 'EXTENSION NF', '#808080', '2026-06-04', '2026-06-30'),
    ('br-rx-f1ab41bbde75', 'MAILING - 16 PAG EL PAIS', 0, 'Ofertas mundialistas - COPETIN BEBIDAS PICADA CARNE', '#ffff00', '2026-06-04', '2026-07-19'),
    ('br-rx-124cc6a50333', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-06-04', '2026-06-07'),
    ('br-rx-f1b19a5cc794', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-06-11', '2026-06-14'),
    ('br-rx-8f8143a27f93', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-06-11', '2026-06-14'),
    ('br-rx-56c430ca2ed2', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-06-18', '2026-06-21'),
    ('br-rx-281693005114', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-06-18', '2026-06-21'),
    ('br-rx-6914f2275de5', 'TÁCTICO (x LOCAL) CM', 0, 'Dia del abuelo (cartelería)', '#ffff00', '2026-06-19', '2026-06-19'),
    ('br-rx-0ed0a42c44a0', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-06-25', '2026-06-28'),
    ('br-rx-f9cf581c86b9', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-06-25', '2026-06-28'),
    ('br-rx-229969b94e57', 'ESPECIAL - CM', 0, 'Especial del vino - 4 pág', '#ffc000', '2026-07-01', '2026-07-19'),
    ('br-rx-200fc2c81d14', 'ESPECIAL - CM', 2, 'Preciazos JULIO', '#ffc000', '2026-07-01', '2026-07-31'),
    ('br-rx-5364dbad5a06', 'TÁCTICO (x LOCAL) CM', 2, 'Mailing julio - HELVETICO', '#ffff00', '2026-07-01', '2026-07-31'),
    ('br-rx-26f8cb4605e2', 'TÁCTICO (x LOCAL) CM', 0, 'Mundo Hogar JULIO - 4 Pág', '#ffff00', '2026-07-01', '2026-07-26'),
    ('br-rx-30f85205cdb6', 'BOMBAS', 0, 'Bombas', '#c65911', '2026-07-02', '2026-07-05'),
    ('br-rx-b760ae866e12', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-07-02', '2026-07-05'),
    ('br-rx-e7b6c488996a', 'BOMBAS', 0, 'Bombas', '#c65911', '2026-07-09', '2026-07-12'),
    ('br-rx-f5324ba92599', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-07-09', '2026-07-12'),
    ('br-rx-10cdc6be4b50', 'BOMBAS', 0, 'Bombas', '#c65911', '2026-07-16', '2026-07-19'),
    ('br-rx-cea8ecd1a00b', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-07-16', '2026-07-19'),
    ('br-rx-0cd035110d57', 'MAILING - 40 PAG EL PAIS', 0, 'A TODO MOTOR - 40 pág', '#00b0f0', '2026-07-20', '2026-07-31'),
    ('br-rx-f98a0fe4a9db', 'BOMBAS', 0, 'Bombas', '#c65911', '2026-07-23', '2026-07-26'),
    ('br-rx-106efee5de5b', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-07-23', '2026-07-26'),
    ('br-rx-d8fe7a74499b', 'TÁCTICO (x LOCAL) CM', 1, 'JUGUETERÍA - DIA DEL NIÑO (8 pág)', '#ffff00', '2026-07-24', '2026-07-31'),
    ('br-rx-442a3ec4edbf', 'BOMBAS', 0, 'Bombas', '#c04f15', '2026-07-30', '2026-07-31'),
    ('br-rx-e2e889d35d53', 'ESPECIAL - CM', 1, 'Preciazos AGOSTO', '#ffc000', '2026-08-01', '2026-08-31'),
    ('br-rx-18e288110683', 'MAILING - 16 PAG EL PAIS', 0, 'A TODO MOTOR - 40 pág', '#00b0f0', '2026-08-01', '2026-08-23'),
    ('br-rx-8cc2836a08a0', 'TÁCTICO (x LOCAL) CM', 1, 'DIA DEL NIÑO', '#ffff00', '2026-08-01', '2026-08-17'),
    ('br-rx-9842195e43e0', 'TÁCTICO (x LOCAL) CM', 2, 'Mailing agosto- HELVETICO', '#ffff00', '2026-08-01', '2026-08-31'),
    ('br-rx-4321cdbc2efa', 'TÁCTICO (x LOCAL) CM', 0, 'Mundo Hogar AGOSTO - 4 Pág', '#ffc000', '2026-08-01', '2026-08-23'),
    ('br-rx-436b532e3586', 'BOMBAS', 0, 'Bombas', '#c65911', '2026-08-06', '2026-08-09'),
    ('br-rx-896a3dd4f54a', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-08-06', '2026-08-09'),
    ('br-rx-c9a83186f9ac', 'BOMBAS', 0, 'Bombas', '#c65911', '2026-08-13', '2026-08-16'),
    ('br-rx-ed4078c32f00', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-08-13', '2026-08-16'),
    ('br-rx-42389c5e1da3', 'ESPECIAL - CM', 0, 'Nostalgia - 4 pág', '#ffc000', '2026-08-20', '2026-08-25'),
    ('br-rx-f521ab1d9e69', 'Super FDS', 0, 'Nostalgia Helvetico - 2 pág', '#ffff00', '2026-08-20', '2026-08-25'),
    ('br-rx-919ccdbfe6fe', 'MAILING - 40 PAG EL PAIS', 0, 'Mailing setiembre - 16 pág', '#c04f15', '2026-08-24', '2026-08-31'),
    ('br-rx-2df912cb8a71', 'TÁCTICO (x LOCAL) CM', 0, 'Mundo Hogar SETIEMBRE - 4 Pág', '#ffff00', '2026-08-24', '2026-09-27'),
    ('br-rx-677a77ede515', 'BOMBAS', 0, 'Bombas', '#c65911', '2026-08-27', '2026-08-30'),
    ('br-rx-69be70fb6a5b', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-08-27', '2026-08-30'),
    ('br-rx-419ddb103ebd', 'ESPECIAL - CM', 0, 'Preciazos SETIEMBRE', '#ffc000', '2026-09-01', '2026-09-30'),
    ('br-rx-7e793387fc56', 'MAILING - 16 PAG EL PAIS', 0, 'Mailing setiembre - 16 pág', '#c04f15', '2026-09-01', '2026-09-27'),
    ('br-rx-f54f1825813d', 'TÁCTICO (x LOCAL) CM', 2, 'Mailing setiembre - HELVETICO', '#ffff00', '2026-09-01', '2026-09-30'),
    ('br-rx-984f838d7864', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-09-03', '2026-09-06'),
    ('br-rx-d26f526e7563', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-09-03', '2026-09-06'),
    ('br-rx-1ad7d6a6fad4', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-09-10', '2026-09-13'),
    ('br-rx-aaabeb7a6831', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-09-10', '2026-09-13'),
    ('br-rx-9077d44ed985', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-09-17', '2026-09-20'),
    ('br-rx-284cab5c5f9b', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-09-17', '2026-09-20'),
    ('br-rx-33f9db2ff80f', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-09-24', '2026-09-27'),
    ('br-rx-adb2054d84d1', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-09-24', '2026-09-27'),
    ('br-rx-2df773ce48f2', 'MAILING - 16 PAG EL PAIS', 0, 'MAILING OCTUBRE - 16 pág (SOLO X 25 + MP)', '#e97132', '2026-09-28', '2026-10-25'),
    ('br-rx-4447c1ff29ec', 'TÁCTICO (x LOCAL) CM', 0, 'Mundo Hogar OCTUBRE - 4 Pág', '#ffc000', '2026-09-28', '2026-10-25'),
    ('br-rx-dc95f144f023', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-10-01', '2026-10-01'),
    ('br-rx-030bc30568a2', 'ESPECIAL - CM', 1, 'Preciazos OCTUBRE', '#ffc000', '2026-10-01', '2026-10-31'),
    ('br-rx-111498c0e25a', 'TÁCTICO (x LOCAL) CM', 1, 'Mailing octubre - HELVETICO', '#ffff00', '2026-10-01', '2026-10-31'),
    ('br-rx-363511cdca38', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-10-08', '2026-10-11'),
    ('br-rx-6bcd7c5d98c9', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-10-08', '2026-10-11'),
    ('br-rx-8c46c63595c9', 'TÁCTICO (x LOCAL) CM', 2, 'Especial Vinos - Helvetico', '#ffff00', '2026-10-09', '2026-10-18'),
    ('br-rx-e35f3ef20e20', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-10-15', '2026-10-18'),
    ('br-rx-ed8944638fad', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-10-15', '2026-10-18'),
    ('br-rx-e23bf69d7701', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-10-22', '2026-10-25'),
    ('br-rx-5b9c6d94ae80', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-10-22', '2026-10-25'),
    ('br-rx-211e30885f92', 'ESPECIAL - CM', 0, 'Halloween (2 pág)', '#ffc000', '2026-10-23', '2026-10-31'),
    ('br-rx-ff510b2fc2fa', 'MAILING - 40 PAG EL PAIS', 0, 'ANIVERSARIO MAILING NOVIEMBRE (SORTEO AUTO + SORTEO) 40 PAG + CONTRATAPA MP', '#a02b93', '2026-10-26', '2026-11-22'),
    ('br-rx-e30ebdb6acba', 'TÁCTICO (x LOCAL) CM', 0, 'Mundo Hogar NOVIEMBRE - 4 Pág', '#ffff00', '2026-10-26', '2026-11-22'),
    ('br-rx-b90ea912240e', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-10-29', '2026-10-29'),
    ('br-rx-655d034b7799', 'ESPECIAL - CM', 1, 'Preciazos NOVIEMBRE', '#ffc000', '2026-11-01', '2026-11-23'),
    ('br-rx-aacc6b8088b2', 'TÁCTICO (x LOCAL) CM', 1, 'Mailing nov - HELVETICO', '#ffff00', '2026-11-01', '2026-11-30'),
    ('br-rx-781f47d3de27', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-11-05', '2026-11-08'),
    ('br-rx-4ec8d4cec13a', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-11-05', '2026-11-08'),
    ('br-rx-e7f2f1200f10', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-11-12', '2026-11-15'),
    ('br-rx-4596cf27c899', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-11-12', '2026-11-15'),
    ('br-rx-e8b733fedb8a', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-11-19', '2026-11-22'),
    ('br-rx-e0935e193abb', 'Super FDS', 0, 'Super FDS', '#00b050', '2026-11-19', '2026-11-22'),
    ('br-rx-2f32b996e212', 'ESPECIAL - CM', 2, 'Despecial Deco Navidad 8 Pag', '#e97132', '2026-11-20', '2026-12-25'),
    ('br-rx-f10755bce9f5', 'ESPECIAL - CM', 0, 'BF GROCERIES Y NF', '#000000', '2026-11-24', '2026-11-30'),
    ('br-rx-201e1fd97a66', 'MAILING - 16 PAG EL PAIS', 0, 'Mailing DICIEMBRE (24 pag) + WHISKY + MP (contratapa)', '#4ea72e', '2026-12-01', '2026-12-31'),
    ('br-rx-bd2e4f4c4a78', 'TÁCTICO (x LOCAL) CM', 2, 'Mailing DIC- SUPER HELVETICO', '#ffff00', '2026-12-01', '2026-12-31'),
    ('br-rx-71ab3bc64cda', 'TÁCTICO (x LOCAL) CM', 1, 'Mundo Hogar DICIEMBRE - 4 Pág', '#ffff00', '2026-12-01', '2026-12-31'),
    ('br-rx-dcca7191250c', 'TÁCTICO (x LOCAL) CM', 0, 'electro sale (confirmar fecha) afiches y cenefas', '#ffff00', '2026-12-01', '2026-12-15'),
    ('br-rx-2d89bff9da98', 'ESPECIAL - CM', 2, 'ESPECIAL JUGUETES y ELECTRO (8 PAG)', '#a02b93', '2026-12-03', '2026-12-31'),
    ('br-rx-da2f364c48c7', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-12-04', '2026-12-07'),
    ('br-rx-304b60cad3d0', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-12-11', '2026-12-14'),
    ('br-rx-36b6de0e8ff8', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-12-18', '2026-12-21'),
    ('br-rx-16c1524f14ce', 'BOMBAS', 0, 'CARNE', '#c65911', '2026-12-25', '2026-12-28')
]


def upgrade() -> None:
    con = op.get_bind()
    nuevas = 0
    for id_, banda, carril, nombre, color, desde, hasta in ACCIONES:
        r = con.execute(sa.text(
            """INSERT INTO calendario_barras (id, mundo, seccion, banda, carril, nombre, color, desde, hasta)
               SELECT :id, :mundo, 'comercial', :banda, :carril, :nombre, :color, :desde, :hasta
               WHERE NOT EXISTS (
                   SELECT 1 FROM calendario_barras
                   WHERE mundo = :mundo AND lower(nombre) = lower(:nombre) AND desde = :desde
               )
               ON CONFLICT (id) DO NOTHING"""
        ), {
            "id": id_, "mundo": MUNDO, "banda": banda, "carril": carril, "nombre": nombre, "color": color,
            "desde": date.fromisoformat(desde), "hasta": date.fromisoformat(hasta),
        })
        nuevas += r.rowcount or 0
    if nuevas:
        # Que las pantallas abiertas de Redexpres se enteren (ver _nueva_revision).
        rev = con.execute(sa.text(
            "UPDATE calendario_revision SET rev = rev + 1 WHERE id = 1 RETURNING rev"
        )).scalar()
        if rev is not None:
            con.execute(sa.text(
                """INSERT INTO calendario_revision_mundo (mundo, rev) VALUES (:mundo, :rev)
                   ON CONFLICT (mundo) DO UPDATE SET rev = EXCLUDED.rev"""
            ), {"mundo": MUNDO, "rev": rev})


def downgrade() -> None:
    # Solo las que siguen como se cargaron: sin tareas ni piezas colgando.
    op.execute(sa.text(
        """DELETE FROM calendario_barras b
           WHERE b.id LIKE 'br-rx-%'
             AND NOT EXISTS (SELECT 1 FROM calendario_tareas t WHERE t.barra_id = b.id)
             AND NOT EXISTS (SELECT 1 FROM calendario_piezas p WHERE p.barra_id = b.id)"""
    ))
