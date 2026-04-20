from flask import (Blueprint, redirect, render_template,
                   request, session, url_for)

from models import Registrant, WebinarConfig, db
from services.scheduler import get_next_webinar_date, is_webinar_open

registrar_bp = Blueprint('registrar', __name__)


@registrar_bp.route('/registrar', methods=['GET', 'POST'])
def register():
    slug = request.args.get('w', '').strip()
    if not slug:
        return render_template('registrar.html', error='Link inválido.', webinar=None), 404

    webinar = WebinarConfig.query.filter_by(slug=slug).first()
    if not webinar:
        return render_template('registrar.html', error='Webinário não encontrado.', webinar=None), 404

    # Se ja tem sessao ativa pra este webinar, pula direto pra sala
    existing_rid = session.get('registrant_id')
    if request.method == 'GET' and existing_rid and session.get('webinar_id') == webinar.id:
        existing = Registrant.query.get(existing_rid)
        if existing and existing.webinar_id == webinar.id:
            return redirect(url_for('sala.sala'))

    # Auto-login por telefone na query string: /registrar?w=SLUG&phone=5511...
    if request.method == 'GET' and request.args.get('phone'):
        ph = request.args.get('phone', '').strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        # Remove +55 / 55 opcional
        if ph.startswith('+'):
            ph = ph[1:]
        # Tenta achar registrant por phone_number com ou sem DDI
        candidates = Registrant.query.filter_by(webinar_id=webinar.id).all()
        for r in candidates:
            rph = (r.phone_number or '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
            rfull = (r.phone_country_code or '').replace('+', '') + rph
            if rph and (ph.endswith(rph) or ph == rfull):
                session['registrant_id'] = r.id
                session['webinar_id'] = webinar.id
                return redirect(url_for('sala.sala'))

    # UTM params — mantidos tanto no GET quanto no POST (request.url preserva query string)
    utm_source = request.args.get('utm_source', '').strip() or None
    utm_medium = request.args.get('utm_medium', '').strip() or None
    utm_campaign = request.args.get('utm_campaign', '').strip() or None

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone_country_code = request.form.get('phone_country_code', '+55').strip() or '+55'
        phone_number = request.form.get('phone_number', '').strip()
        email = request.form.get('email', '').strip().lower()  # compatibilidade retroativa

        if not name or (not phone_number and not email):
            _nd = get_next_webinar_date(
                day_of_week=webinar.day_of_week or 1,
                start_hour=webinar.start_hour or 19,
                start_minute=webinar.start_minute or 0,
            )
            _is_open = is_webinar_open(_nd) if _nd else False
            return render_template('registrar.html', webinar=webinar,
                                   error='Preencha nome e telefone.', is_open=_is_open)

        # Busca registrante por telefone (prioritário) ou email
        registrant = None
        if phone_number:
            registrant = Registrant.query.filter_by(
                phone_number=phone_number, webinar_id=webinar.id
            ).first()
        if not registrant and email:
            registrant = Registrant.query.filter_by(
                email=email, webinar_id=webinar.id
            ).first()

        if not registrant:
            webinar_date = get_next_webinar_date(
                day_of_week=webinar.day_of_week or 1,
                start_hour=webinar.start_hour or 19,
                start_minute=webinar.start_minute or 0,
            )
            naive_dt = webinar_date.replace(tzinfo=None)

            registrant = Registrant(
                name=name,
                email=email or None,
                phone_country_code=phone_country_code,
                phone_number=phone_number or None,
                webinar_id=webinar.id,
                webinar_date=naive_dt,
                utm_source=utm_source,
                utm_medium=utm_medium,
                utm_campaign=utm_campaign,
            )
            db.session.add(registrant)
            db.session.commit()
        else:
            changed = False
            if registrant.name != name:
                registrant.name = name
                changed = True
            if phone_number and registrant.phone_number != phone_number:
                registrant.phone_number = phone_number
                registrant.phone_country_code = phone_country_code
                changed = True
            # Atualiza UTMs se ainda não tiver
            if utm_source and not registrant.utm_source:
                registrant.utm_source = utm_source
                registrant.utm_medium = utm_medium
                registrant.utm_campaign = utm_campaign
                changed = True
            if changed:
                db.session.commit()

        session.permanent = False
        session['registrant_id'] = registrant.id
        session['webinar_id'] = webinar.id

        return redirect(url_for('sala.sala'))

    # GET
    next_date = get_next_webinar_date(
        day_of_week=webinar.day_of_week or 1,
        start_hour=webinar.start_hour or 19,
        start_minute=webinar.start_minute or 0,
    )
    is_open = is_webinar_open(next_date) if next_date else False
    return render_template('registrar.html', webinar=webinar, error=None, is_open=is_open)
