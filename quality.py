# This file is part of Tryton.  The COPYRIGHT file at the top level of this
# repository contains the full copyright notices and license terms.
from datetime import datetime

from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool
from trytond.pyson import Eval
from trytond.transaction import Transaction

__all__ = [
    'QualityControlRuleOperation',
    'QualityControlRuleProductTemplate',
    'QualityControlRule',
]


class QualityControlRuleOperation(ModelSQL):
    'Quality Control Rule - Operation'
    __name__ = 'quality.control.rule-production.routing.operation'

    rule = fields.Many2One(
        'quality.control.rule', 'Rule', required=True,
        ondelete='CASCADE')
    operation = fields.Many2One(
        'production.routing.operation', 'Operation', required=True,
        ondelete='CASCADE')


class QualityControlRuleProductTemplate(ModelSQL):
    'Quality Control Rule - Product Template'
    __name__ = 'quality.control.rule-product.template'

    rule = fields.Many2One(
        'quality.control.rule', 'Rule', required=True,
        ondelete='CASCADE')
    template = fields.Many2One(
        'product.template', 'Template', required=True,
        ondelete='CASCADE')


class QualityControlRule(ModelSQL, ModelView):
    'Quality Control Rule'
    __name__ = 'quality.control.rule'

    name = fields.Char('Name', required=True, translate=True)
    company = fields.Many2One('company.company', 'Company')
    quality_template = fields.Many2One(
        'quality.template', 'Quality Template', required=True)
    operations = fields.Many2Many(
        'quality.control.rule-production.routing.operation', 'rule',
        'operation', 'Operations')
    products = fields.Many2Many(
        'quality.control.rule-product.template', 'rule', 'template',
        'Products')
    document = fields.Many2One(
        'ir.model', 'Document', required=True)
    trigger_document = fields.Many2One(
        'ir.model', 'Trigger Document', required=True,)
    creation_moment = fields.Selection([
            ('manual', 'Manual'),
            ('create', 'Al crear'),
            ('state', 'Dependiendo del estado'),
            ('period', 'Período de tiempo'),
            ('records', 'Cada x registros'),
        ], 'Creation Moment', required=True)
    trigger_state = fields.Selection(
        'get_trigger_states', 'Trigger State',
        selection_change_with=['trigger_document'], states={
            'required': Eval('creation_moment') == 'state',
            'invisible': Eval('creation_moment') != 'state',
            })
    period_hours = fields.Integer(
        'Hours Difference', states={
            'required': Eval('creation_moment') == 'period',
            'invisible': Eval('creation_moment') != 'period',
            })
    record_interval = fields.Integer(
        'Record Interval', states={
            'required': Eval('creation_moment') == 'records',
            'invisible': Eval('creation_moment') != 'records',
            })

    @staticmethod
    def default_creation_moment():
        return 'manual'

    @staticmethod
    def _get_id(record):
        return getattr(record, 'id', record)

    @classmethod
    def _get_rule_operation(cls, document):
        operation = getattr(document, 'operation', None)
        if operation:
            return operation
        work = getattr(document, 'work', None)
        if work:
            operation = getattr(work, 'operation', None)
            if operation:
                return operation
        return None

    @classmethod
    def _get_rule_product(cls, document):
        product = getattr(document, 'product', None)
        if product:
            return getattr(product, 'template', product)
        production = getattr(document, 'production', None)
        if production and getattr(production, 'product', None):
            return production.product.template
        work = getattr(document, 'work', None)
        if work and getattr(work, 'production', None):
            product = getattr(work.production, 'product', None)
            if product:
                return product.template
        return None

    @staticmethod
    def _get_product_template(product):
        if product and getattr(product, '__name__', None) == 'product.product':
            return product.template
        return product

    @fields.depends('trigger_document')
    def get_trigger_states(self):
        if not self.trigger_document:
            return [('', '')]
        Model = Pool().get(self.trigger_document.model)
        states = getattr(Model, 'state', None)
        if not states:
            return [('', '')]
        if hasattr(states, 'selection'):
            return [('', '')] + list(states.selection)
        return [('', '')]

    @classmethod
    def _get_last_test(cls, document, company=None):
        pool = Pool()
        QualityTest = pool.get('quality.test')
        domain = [('document', '=', document)]
        if company:
            company_id = getattr(company, 'id', company)
            domain.append(('company', '=', company_id))
        tests = QualityTest.search(domain, order=[
                ('test_date', 'DESC'),
                ('id', 'DESC'),
                ], limit=1)
        return tests[0] if tests else None

    @classmethod
    def _get_period_due_count(cls, rule, document, company=None, now=None):
        if not rule.period_hours or rule.period_hours <= 0:
            return 0
        now = now or datetime.now()
        test = cls._get_last_test(document, company=company)
        if not test or not test.test_date:
            return 1
        elapsed_hours = (now - test.test_date).total_seconds() / 3600
        if elapsed_hours < rule.period_hours:
            return 0
        return int(elapsed_hours // rule.period_hours)

    @classmethod
    def _get_record_due_count(cls, rule, document, trigger_document_model,
            company=None, now=None):
        if not rule.record_interval or rule.record_interval <= 0:
            return 0
        now = now or datetime.now()
        test = cls._get_last_test(document, company=company)
        last_test_date = test.test_date if test else None
        pool = Pool()
        TriggerModel = pool.get(trigger_document_model)
        domain = []
        if last_test_date:
            domain.append(('create_date', '>', last_test_date))
        if company and 'company' in TriggerModel._fields:
            company_id = getattr(company, 'id', company)
            domain.append(('company', '=', company_id))
        count = TriggerModel.search_count(domain)
        if count < rule.record_interval:
            return 0
        return int(count // rule.record_interval)

    @classmethod
    def _create_test_records(cls, document, templates, company):
        pool = Pool()
        QualityTest = pool.get('quality.test')
        tests = []
        for template in templates:
            test = QualityTest(
                test_date=datetime.now(),
                document=document,
                templates=[template],
                company=company,
            )
            tests.append(test)
        if tests:
            QualityTest.save(tests)
            QualityTest.apply_templates(tests)
        return tests

    @classmethod
    def get_quality_rules(cls, document_model=None,
            trigger_document_model=None, creation_moment=None, state=None,
            company=None, operation=None, product=None):
        rules = []
        company_id = getattr(company, 'id', company)
        operation_id = cls._get_id(operation)
        product_id = cls._get_id(cls._get_product_template(product))
        for rule in cls.search([]):
            if company_id and rule.company and rule.company.id != company_id:
                continue
            rule_document_model = rule.document.model if rule.document else None
            if document_model and rule_document_model != document_model:
                continue
            rule_trigger_document_model = (
                rule.trigger_document.model if rule.trigger_document else None)
            if (trigger_document_model and
                    rule_trigger_document_model != trigger_document_model):
                continue
            if creation_moment and rule.creation_moment != creation_moment:
                continue
            if state and rule.creation_moment == 'state':
                if rule.trigger_state not in (None, '', state):
                    continue
            if rule.operations:
                if not operation_id:
                    continue
                rule_operation_ids = {
                    cls._get_id(operation)
                    for operation in rule.operations
                }
                if operation_id not in rule_operation_ids:
                    continue
            if rule.products:
                if not product_id:
                    continue
                rule_product_ids = {
                    cls._get_id(product)
                    for product in rule.products
                }
                if product_id not in rule_product_ids:
                    continue
            rules.append(rule)
        return rules

    @classmethod
    def get_quality_templates(cls, document_model=None,
            trigger_document_model=None, creation_moment=None, state=None,
            company=None, operation=None, product=None):
        templates = []
        seen = set()
        for rule in cls.get_quality_rules(
                document_model=document_model,
                trigger_document_model=trigger_document_model,
                creation_moment=creation_moment, state=state,
                company=company, operation=operation, product=product):
            template = rule.quality_template
            if not template or template.id in seen:
                continue
            seen.add(template.id)
            templates.append(template)
        return templates

    @classmethod
    def create_quality_tests(cls, document, document_model=None,
            trigger_document_model=None, creation_moment=None, state=None,
            company=None, operation=None, product=None):
        pool = Pool()
        QualityTest = pool.get('quality.test')

        document_model = document_model or getattr(document, '__name__', None)
        trigger_document_model = (
            trigger_document_model or document_model)
        company = company or getattr(document, 'company', None)
        if company is None:
            company = Transaction().context.get('company')
        operation = operation or cls._get_rule_operation(document)
        product = cls._get_product_template(
            product or cls._get_rule_product(document))
        templates = cls.get_quality_templates(
            document_model=document_model,
            trigger_document_model=trigger_document_model,
            creation_moment=creation_moment, state=state,
            company=company, operation=operation, product=product)
        if not templates:
            return []

        tests = []
        existing_template_ids = set()
        if creation_moment not in ('period', 'records'):
            for test in QualityTest.search([('document', '=', document)]):
                for template in test.templates:
                    existing_template_ids.add(template.id)

        rule_templates = set()
        for rule in cls.get_quality_rules(
                document_model=document_model,
                trigger_document_model=trigger_document_model,
                creation_moment=creation_moment, state=state,
                company=company, operation=operation, product=product):
            template = rule.quality_template
            if not template or template.id in rule_templates:
                continue
            rule_templates.add(template.id)

            if rule.creation_moment == 'period':
                due_count = cls._get_period_due_count(
                    rule, document, company=company)
                if not due_count:
                    continue
                tests.extend(cls._create_test_records(
                    document, [template] * due_count, company))
                continue

            if rule.creation_moment == 'records':
                due_count = cls._get_record_due_count(
                    rule, document, trigger_document_model,
                    company=company)
                if not due_count:
                    continue
                tests.extend(cls._create_test_records(
                    document, [template] * due_count, company))
                continue

            if template.id in existing_template_ids:
                continue
            tests.extend(cls._create_test_records(
                document, [template], company))
            existing_template_ids.add(template.id)
        return tests


def register():
    Pool.register(
        QualityControlRuleOperation,
        QualityControlRuleProductTemplate,
        QualityControlRule,
        module='quality_control_rules', type_='model')
