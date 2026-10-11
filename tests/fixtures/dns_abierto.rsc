# export de prueba: resolutor DNS abierto y sin filtro de entrada
/ip dns
set allow-remote-requests=yes servers=8.8.8.8,8.8.4.4

/ip firewall filter
add action=accept chain=input comment="permitir SSH" dst-port=22 protocol=tcp
