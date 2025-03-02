from natural20.die_roll import DieRoll
from natural20.item_library.object import Object

class Note(Object):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties)
        self.properties = properties

    def investigate_details(self, entity):
        investigate_details = []

        if self.properties.get('investigation'):
            for investigation_type, details in self.properties.get('investigation').items():
                if self.check_results.get(entity) and self.check_results.get(entity).get(investigation_type):
                    if self.check_results.get(entity).get(investigation_type) >= details.get('dc'):
                        investigate_details.append(details.get('success'))
                    else:
                        if details.get('failure'):
                            investigate_details.append(details.get('failure'))

                return details
        return None


    def build_map(self, action, action_object):
        if action == 'medicine_check':
            return action_object

    def use(self, entity, result, session=None):
        action = result.get('action')
        if action == 'check':
            if entity not in self.check_results:
                self.check_results[entity] = {}
            self.check_results[entity][result["check_type"]] = result.get('roll')

    def resolve(self, entity, action, other_params, opts=None):
        if opts is None:
            opts = {}

        if action=='investigate':
            return { 
                     'type': 'investigate',
                     'result': self.properties.get('investigation')
                    }

        for check_type in ['medicine_check', 'investigation_check']:
            check_type_roll = entity[check_type](opts.get('battle'))
            return {
                     "action" : "check",
                     "check_type" : check_type,
                     "roll" : check_type_roll,
                     "dc" : self.properties.get(check_type).get('dc'),
                     "success" : check_type_roll.result() >= self.properties.get(check_type).get('dc')
                    }
