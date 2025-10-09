# server.py
import os
from flask import Flask, render_template
from config import Config

class PDFWebServer:
    def __init__(self, import_name, config_class=Config):
        """
        Inizializza il server web Flask.
        :param import_name: Il nome dell'applicazione, di solito __name__.
        :param config_class: La classe di configurazione da usare.
        """
        self.app = Flask(import_name)
        self.app.config.from_object(config_class)
        
        # Rotta principale per la homepage
        self.app.add_url_rule('/', 'index', self.index)
        
        # Registra tutti i servizi (Blueprints) in modo dinamico
        self._register_services()

    def _register_services(self):
        """
        Scansiona la cartella 'services' e registra ogni Blueprint trovato.
        Questo rende l'applicazione modulare.
        """
        services_path = os.path.join(os.path.dirname(__file__), 'services')
        for service_name in os.listdir(services_path):
            service_dir = os.path.join(services_path, service_name)
            # Controlla che sia una directory e che contenga un __init__.py
            if os.path.isdir(service_dir) and '__init__.py' in os.listdir(service_dir):
                try:
                    # Importa il modulo (es. services.merge)
                    module = __import__(f'services.{service_name}', fromlist=['bp'])
                    # Ottieni il Blueprint dal modulo
                    blueprint = getattr(module, 'bp')
                    # Registra il Blueprint nell'app Flask
                    self.app.register_blueprint(blueprint)
                    print(f"Servizio '{service_name}' registrato con successo.")
                except (ImportError, AttributeError) as e:
                    print(f"Impossibile registrare il servizio '{service_name}': {e}")

    def index(self):
        """
        Mostra la homepage con la lista dei servizi disponibili.
        La lista è generata dinamicamente dai Blueprint registrati.
        """
        services = []
        for rule in self.app.url_map.iter_rules():
            # Le regole dei nostri blueprint avranno un endpoint come 'nome_servizio.index'
            if '.' in rule.endpoint and rule.endpoint.endswith('.index'):
                service_name = rule.endpoint.split('.')[0].capitalize()
                service_url = rule.rule
                services.append({'name': service_name, 'url': service_url})
        
        return render_template('index.html', services=services)

    def run(self, debug=True, port=5000):
        """Avvia il server di sviluppo Flask."""
        self.app.run(debug=debug, port=port)
