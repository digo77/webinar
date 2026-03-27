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

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()

        if not name or not email:
            _nd = get_next_webinar_date(
                day_of_week=webinar.day_of_week or 1,
                start_hour=webinar.start_hour or 19,
                start_minute=webinar.start_minute or 0,
            )
            _is_open = is_webinar_open(_nd) if _nd else False
            return render_template('registrar.html', webinar=webinar,
                                   error='Preencha nome e e-mail.', is_open=_is_open)

        # Busca ou cria o registrante (por email + webinar)
        registrant = Registrant.query.filter_by(
            email=email, webinar_id=webinar.id
        ).first()

        if not registrant:
            # Calcula próxima data do webinário
            webinar_date = get_next_webinar_date(
                day_of_week=webinar.day_of_week or 1,
                start_hour=webinar.start_hour or 19,
                start_minute=webinar.start_minute or 0,
            )
            # Armazena como naive BRT (compatível com is_webinar_open)
            naive_dt = webinar_date.replace(tzinfo=None)

            registrant = Registrant(
                name=name,
                email=email,
                webinar_id=webinar.id,
                webinar_date=naive_dt,
            )
            db.session.add(registrant)
            db.session.commit()
        else:
            # Atualiza nome se necessário
            if registrant.name != name:
                registrant.name = name
                db.session.commit()

        # Salva na sessão Flask
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
