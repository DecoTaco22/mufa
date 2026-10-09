# export de prueba: resolutor DNS abierto pero filtrado en el borde
/ip dns
set allow-remote-requests=yes servers=8.8.8.8,8.8.4.4

/ip firewall filter
add action=drop chain=input comment="MUFA-DNS-001" dst-port=53 in-interface-list=WAN protocol=udp
add action=accept chain=input comment="permitir establecidas" connection-state=established,related
