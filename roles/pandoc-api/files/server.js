'use strict'
const express    = require('express')
const { execFile } = require('child_process')
const fs         = require('fs')
const path       = require('path')
const os         = require('os')

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, WidthType, BorderStyle, ShadingType,
  convertMillimetersToTwip
} = require('docx')

const app = express()
app.use(express.json({ limit: '10mb' }))

// ─── SOP data (mirrors mop-get.json) ─────────────────────────────────────────
const SOPS = {
  '10-SOP': {
    nom: 'Vérification OOB & Accès management',
    ref: 'OPSSD-03.03.S0.10-SOP',
    objectif: "Confirmer l'accès OOB, Lightsoft et les accès management. Prérequis universel — à déclencher en premier sur tout incident.",
    steps: [
      "Ping gateway OOB — Depuis la station NOC, ping 10.0.0.1. Timeout = problème réseau OOB.",
      "Ouvrir Lightsoft — URL: http://lightsoft.internal — login admin.",
      "Vérifier alarmes actives — Menu Supervision > Alarmes. Noter criticité et heure.",
      "Tester accès SSH équipements — ssh admin@<node-ip> sur chaque châssis concerné. Timeout = vérifier règles firewall Lugos.",
      "Vérifier firewall Lugos si CLI KO — lugos show rules | grep management. Confirmer IPs NOC autorisées."
    ]
  },
  '11-SOP': {
    nom: 'Analyse Optique SFP',
    ref: 'OPSSD-03.03.S0.11-SOP',
    objectif: "Analyser les compteurs PM (FEC/BER/ES/SES) et la puissance optique SFP sur les ports OTN.",
    steps: [
      "Lightsoft > PM Counters — Sélectionner port > onglet Performance Monitoring > période 24h.",
      "Lire FEC corrected/uncorrected — FEC corrected en hausse = dégradation optique. Uncorrected > 0 = critique.",
      "Vérifier BER pre/post FEC — Pre-FEC BER > 1e-3 = problème signal. Post-FEC BER > 0 = urgence.",
      "Analyser ES / SES sur 24h — ES < 0.4% sur 24h (ITU-T G.826). SES < 0.05%. Dépassement = dégradation confirmée.",
      "Mesurer puissance optique SFP — Power meter sur connecteur d'entrée port concerné. Comparer aux specs SFP constructeur."
    ]
  },
  '12-SOP': {
    nom: 'Test Viavi E2E',
    ref: 'OPSSD-03.03.S0.12-SOP',
    objectif: "Test de validation RFC 2544 / OTU2 E2E après remplacement physique ou troubleshooting client.",
    steps: [
      "Connecter le Viavi MTS-5800 — Port OTU2 du MTS-5800 sur le port UNI/NNI à valider. Mode: OTU2 10.7G.",
      "Configurer le test RFC 2544 — Throughput, Latency, Frame Loss, Back-to-Back. Taille trames: 64, 128, 256, 512, 1024, 1518 bytes.",
      "Lancer le test — Durée minimale: 60s par taille de trame. Enregistrer les résultats.",
      "Valider les seuils — Throughput > 99.9%. Latency < 1ms. Frame Loss = 0%. B2B > 90 frames.",
      "Exporter le rapport Viavi — MTS-5800 > Reports > Export PDF. Joindre au rapport d'intervention final."
    ]
  },
  '13-SOP': {
    nom: 'Remplacement matériel (carte + SFP)',
    ref: 'OPSSD-03.03.S0.13-SOP',
    objectif: "Remplacement d'une carte service (LB/HB/VHB) ou d'un SFP défectueux sur châssis Ribbon Apollo.",
    steps: [
      "Confirmer la panne — Lightsoft : carte en état FAILED ou MISMATCH, ou SFP en LOS persistant.",
      "Prévoir le spare — Vérifier stock spare. Référence carte : étiquette châssis. Même référence SFP (λ, portée).",
      "Informer les clients affectés — Identifier les ports UNI/NNI impactés. Notifier avant intervention.",
      "Extraire le matériel défaillant — Déverrouiller la carte ou SFP. ESD obligatoire. Tirer avec précaution.",
      "Insérer le matériel de remplacement — Insérer jusqu'au clic. Lightsoft : état IN-SERVICE sous 2 min.",
      "Valider E2E — 12-SOP (Test Viavi E2E) obligatoire pour confirmation service."
    ]
  },
  '14-SOP': {
    nom: 'Diagnostic signal OTN (OSNR + FEC/BER)',
    ref: 'OPSSD-03.03.S0.14-SOP',
    objectif: "Diagnostic complet signal OTN : OSNR, SPAN LOSS, FEC/BER et gestion bascule OLP.",
    steps: [
      "Ouvrir Lightsoft > Supervision — Menu Supervision > Vue topologie > sélectionner le lien concerné.",
      "Relever OSNR — Colonne OSNR doit être > 12 dB sur chaque canal. Valeur < 10 dB = critique.",
      "Mesurer SPAN LOSS — Span Loss = différence Tx/Rx en dBm. Seuil normal < 20 dB.",
      "Vérifier protection OLP — Lightsoft > Protection > état Working/Protect. Si bascule active : identifier chemin Working et cause.",
      "Inspecter connecteurs et SFP — Si SPAN LOSS élevé : nettoyer connecteurs SC/PC (kit IBC). Power meter sur port."
    ]
  },
  '15-SOP': {
    nom: 'Escalade Constructeur (Ribbon)',
    ref: 'OPSSD-03.03.S0.15-SOP',
    objectif: "Ouvrir un SR Ribbon TAC si l'incident n'est pas résolu après 10-SOP ou 11-SOP.",
    steps: [
      "Préparer les informations — Numéro de châssis, version logicielle, alarmes actives, logs GCC.",
      "Créer le SR — Portal : support.ribboncommunications.com > Create Service Request.",
      "Envoyer les logs — Lightsoft > Export > System Logs (24h). Joindre au SR."
    ]
  },
  '16-SOP': {
    nom: 'Escalade Supervision (Lugos)',
    ref: 'OPSSD-03.03.S0.16-SOP',
    objectif: "Escalade vers l'équipe supervision Lugos si l'incident persiste après 10-SOP.",
    steps: [
      "Documenter l'incident — Consigner symptômes, heure de début, SOPs déjà appliquées et résultats.",
      "Contacter Lugos NOC — Ticket portail Lugos avec logs Lightsoft. Indiquer criticité et clients impactés.",
      "Suivre le cas — Mettre à jour le ticket toutes les 30 min. Escalade niveau 2 si pas de réponse sous 1h."
    ]
  },
  '17-SOP': {
    nom: 'Escalade Opérateur',
    ref: 'OPSSD-03.03.S0.17-SOP',
    objectif: "Escalade vers l'opérateur (Cogent / EuNetwork) pour incident LOS ou bascule OLP non résolu.",
    steps: [
      "Confirmer l'origine opérateur — Isoler : LOS sur plusieurs NNI ou OLP déclenché côté opérateur (pas côté équipement).",
      "Contacter le NOC opérateur — Cogent NOC : ticket portail / hotline. EuNetwork NOC : portail dédié.",
      "Fournir les métriques — OSNR, puissance Rx, heure et durée de l'incident. Résultats 14-SOP joints.",
      "Documenter — Référence ticket opérateur dans le rapport d'incident final."
    ]
  }
}

const PHASE_MAP = { '10-SOP': 1, '11-SOP': 2, '12-SOP': 5, '13-SOP': 3, '14-SOP': 2, '15-SOP': 4, '16-SOP': 4, '17-SOP': 4 }
const PHASES = {
  1: { nom: 'Pré-requis',    desc: 'Vérifier accès OOB et management avant toute intervention.',                    color: '1a3a5c' },
  2: { nom: 'Diagnostic',    desc: 'Identifier la cause racine par des vérifications techniques ciblées.',          color: '2c5f8a' },
  3: { nom: 'Intervention',  desc: 'Remplacer ou reconfigurer le matériel défaillant.',                             color: '3a5a8a' },
  4: { nom: 'Escalade',      desc: "Escalader vers constructeur, supervision ou opérateur si l'incident persiste.", color: '4a4a8a' },
  5: { nom: 'Validation',    desc: 'Valider la conformité du lien restauré par test E2E.',                          color: '2e7d32' }
}

const CRIT_COLORS = { MINEUR: '2e7d32', MAJEUR: 'e65100', CRITIQUE: 'b71c1c' }
const NAVY = '0d2b52'
const BORDER_NONE = { style: BorderStyle.NONE, size: 0, color: 'auto' }

// ─── helpers ─────────────────────────────────────────────────────────────────

function mm(v) { return convertMillimetersToTwip(v) }

function hLine(color = 'D0D8E8') {
  return {
    top:    { style: BorderStyle.NONE, size: 0 },
    bottom: { style: BorderStyle.SINGLE, size: 6, color },
    left:   { style: BorderStyle.NONE, size: 0 },
    right:  { style: BorderStyle.NONE, size: 0 }
  }
}

function noBorder() {
  return { top: BORDER_NONE, bottom: BORDER_NONE, left: BORDER_NONE, right: BORDER_NONE }
}

function thinBorder(color = 'E0E6F0') {
  const b = { style: BorderStyle.SINGLE, size: 4, color }
  return { top: b, bottom: b, left: b, right: b }
}

function para(runs, opts = {}) {
  return new Paragraph({ children: Array.isArray(runs) ? runs : [runs], ...opts })
}

function run(text, opts = {}) { return new TextRun({ text, ...opts }) }

function spacer(sz = 60) {
  return new Paragraph({ children: [], spacing: { before: sz, after: sz } })
}

// A full-width single-cell banner row
function bannerRow(text, bgColor, textColor = 'FFFFFF', bold = true, size = 22) {
  return new TableRow({
    children: [new TableCell({
      shading: { fill: bgColor, type: ShadingType.SOLID },
      borders: noBorder(),
      width: { size: 100, type: WidthType.PERCENTAGE },
      children: [para(run(text, { color: textColor, bold, size, font: 'Segoe UI' }))]
    })]
  })
}

// Two-column key-value row inside a meta table
function metaRow(key, value, bgColor = 'F8F9FB') {
  return new TableRow({
    children: [
      new TableCell({
        shading: { fill: bgColor, type: ShadingType.SOLID },
        borders: noBorder(),
        width: { size: 35, type: WidthType.PERCENTAGE },
        children: [para(run(key, { bold: true, color: '444444', size: 18, font: 'Segoe UI' }))]
      }),
      new TableCell({
        shading: { fill: bgColor, type: ShadingType.SOLID },
        borders: noBorder(),
        width: { size: 65, type: WidthType.PERCENTAGE },
        children: [para(run(value || '—', { color: '1a1a1a', size: 18, font: 'Segoe UI' }))]
      })
    ]
  })
}

// ─── /convert/sop-to-docx ────────────────────────────────────────────────────

app.post('/convert/sop-to-docx', async (req, res) => {
  try {
    const body = req.body || {}
    const {
      incident_id, incident_type, sous_type, criticite,
      site, equipment, technicien, date_intervention, heure_debut,
      symptome, impact, cause_probable,
      alarme_lightsoft, alarme_vizee
    } = body

    const sopsInput = body.sops
    const sopsArr = typeof sopsInput === 'string'
      ? sopsInput.split(',').map(s => s.trim()).filter(Boolean)
      : (Array.isArray(sopsInput) ? sopsInput : [])

    const docId = 'MOP-' + (incident_id || 'XXX') + '-SOP'
    const critColor = CRIT_COLORS[criticite] || CRIT_COLORS.MAJEUR
    const genTime = new Date().toISOString().replace('T', ' ').slice(0, 16) + ' UTC'

    const sections = []

    // ── 1. Document header ──────────────────────────────────────────────────
    sections.push(
      new Table({
        width: { size: 100, type: WidthType.PERCENTAGE },
        borders: { top: BORDER_NONE, bottom: { style: BorderStyle.SINGLE, size: 12, color: NAVY }, left: BORDER_NONE, right: BORDER_NONE, insideH: BORDER_NONE, insideV: BORDER_NONE },
        rows: [new TableRow({
          children: [
            new TableCell({
              borders: noBorder(),
              width: { size: 70, type: WidthType.PERCENTAGE },
              children: [
                para(run('SOPs OPÉRATIONNELLES NOC', { bold: true, size: 36, color: NAVY, font: 'Segoe UI' })),
                para(run((incident_type || '') + (sous_type ? ' — ' + sous_type : ''), { size: 20, color: '666666', font: 'Segoe UI' }))
              ]
            }),
            new TableCell({
              borders: noBorder(),
              width: { size: 30, type: WidthType.PERCENTAGE },
              children: [
                para(run(docId, { bold: true, size: 28, color: NAVY, font: 'Segoe UI' }), { alignment: AlignmentType.RIGHT }),
                para(run((date_intervention || '____') + ' ' + (heure_debut || ''), { size: 18, color: '888888', font: 'Segoe UI' }), { alignment: AlignmentType.RIGHT }),
                para(run('Généré : ' + genTime, { size: 16, color: 'aaaaaa', font: 'Segoe UI' }), { alignment: AlignmentType.RIGHT })
              ]
            })
          ]
        })]
      }),
      spacer(80)
    )

    // ── 2. Criticité banner ─────────────────────────────────────────────────
    sections.push(
      new Table({
        width: { size: 100, type: WidthType.PERCENTAGE },
        borders: { top: { style: BorderStyle.SINGLE, size: 12, color: critColor }, bottom: { style: BorderStyle.SINGLE, size: 4, color: critColor }, left: { style: BorderStyle.SINGLE, size: 18, color: critColor }, right: BORDER_NONE, insideH: BORDER_NONE, insideV: BORDER_NONE },
        rows: [new TableRow({
          children: [
            new TableCell({
              shading: { fill: 'F8F8F8', type: ShadingType.SOLID },
              borders: noBorder(),
              width: { size: 20, type: WidthType.PERCENTAGE },
              children: [
                para(run('CRITICITÉ', { size: 16, color: '888888', font: 'Segoe UI' })),
                para(run(criticite || 'MAJEUR', { bold: true, size: 26, color: critColor, font: 'Segoe UI' }))
              ]
            }),
            new TableCell({
              shading: { fill: 'F8F8F8', type: ShadingType.SOLID },
              borders: noBorder(),
              width: { size: 40, type: WidthType.PERCENTAGE },
              children: [
                para(run('CATÉGORIE', { size: 16, color: '888888', font: 'Segoe UI' })),
                para(run(incident_type || '—', { size: 20, color: '444444', font: 'Segoe UI' }))
              ]
            }),
            new TableCell({
              shading: { fill: 'F8F8F8', type: ShadingType.SOLID },
              borders: noBorder(),
              width: { size: 40, type: WidthType.PERCENTAGE },
              children: [
                para(run('IMPACT', { size: 16, color: '888888', font: 'Segoe UI' })),
                para(run(impact || '—', { size: 20, color: '444444', font: 'Segoe UI' }))
              ]
            })
          ]
        })]
      }),
      spacer(80)
    )

    // ── 3. Meta grid ────────────────────────────────────────────────────────
    sections.push(
      new Table({
        width: { size: 100, type: WidthType.PERCENTAGE },
        borders: { top: BORDER_NONE, bottom: BORDER_NONE, left: BORDER_NONE, right: BORDER_NONE, insideH: BORDER_NONE, insideV: { style: BorderStyle.SINGLE, size: 4, color: 'FFFFFF' } },
        rows: [new TableRow({
          children: [
            // Left: Incident info
            new TableCell({
              shading: { fill: 'F8F9FB', type: ShadingType.SOLID },
              borders: thinBorder(),
              width: { size: 50, type: WidthType.PERCENTAGE },
              children: [
                para(run('INCIDENT', { bold: true, size: 17, color: NAVY, font: 'Segoe UI' }), { border: hLine() }),
                spacer(20),
                ...([
                  ['ID Incident', incident_id],
                  ['Type', incident_type],
                  ['Sous-type', sous_type],
                  ['Criticité', criticite]
                ].map(([k, v]) => new Table({
                  width: { size: 100, type: WidthType.PERCENTAGE },
                  borders: { top: BORDER_NONE, bottom: BORDER_NONE, left: BORDER_NONE, right: BORDER_NONE, insideH: BORDER_NONE, insideV: BORDER_NONE },
                  rows: [metaRow(k, v, 'F8F9FB')]
                })))
              ]
            }),
            // Right: Site / technicien
            new TableCell({
              shading: { fill: 'F8F9FB', type: ShadingType.SOLID },
              borders: thinBorder(),
              width: { size: 50, type: WidthType.PERCENTAGE },
              children: [
                para(run('CONTEXTE INTERVENTION', { bold: true, size: 17, color: NAVY, font: 'Segoe UI' }), { border: hLine() }),
                spacer(20),
                ...([
                  ['Site', site],
                  ['Équipement', equipment],
                  ['Technicien', technicien],
                  ['Date / Heure', (date_intervention || '') + ' ' + (heure_debut || '')]
                ].map(([k, v]) => new Table({
                  width: { size: 100, type: WidthType.PERCENTAGE },
                  borders: { top: BORDER_NONE, bottom: BORDER_NONE, left: BORDER_NONE, right: BORDER_NONE, insideH: BORDER_NONE, insideV: BORDER_NONE },
                  rows: [metaRow(k, v, 'F8F9FB')]
                })))
              ]
            })
          ]
        })]
      }),
      spacer(80)
    )

    // ── 4. Symptôme / Cause ─────────────────────────────────────────────────
    if (symptome || cause_probable) {
      sections.push(
        new Table({
          width: { size: 100, type: WidthType.PERCENTAGE },
          borders: { top: BORDER_NONE, bottom: BORDER_NONE, left: BORDER_NONE, right: BORDER_NONE, insideH: BORDER_NONE, insideV: { style: BorderStyle.SINGLE, size: 4, color: 'FFFFFF' } },
          rows: [new TableRow({
            children: [
              new TableCell({
                shading: { fill: 'FFF8E1', type: ShadingType.SOLID },
                borders: { ...thinBorder('FFE082'), left: { style: BorderStyle.SINGLE, size: 18, color: 'F59E0B' } },
                width: { size: 50, type: WidthType.PERCENTAGE },
                children: [
                  para(run('SYMPTÔME', { bold: true, size: 17, color: 'B45309', font: 'Segoe UI' })),
                  para(run(symptome || '—', { size: 19, color: '1a1a1a', font: 'Segoe UI' }))
                ]
              }),
              new TableCell({
                shading: { fill: 'FFF8E1', type: ShadingType.SOLID },
                borders: { ...thinBorder('FFE082'), left: { style: BorderStyle.SINGLE, size: 18, color: 'F59E0B' } },
                width: { size: 50, type: WidthType.PERCENTAGE },
                children: [
                  para(run('CAUSE PROBABLE', { bold: true, size: 17, color: 'B45309', font: 'Segoe UI' })),
                  para(run(cause_probable || '—', { size: 19, color: '1a1a1a', font: 'Segoe UI' }))
                ]
              })
            ]
          })]
        }),
        spacer(80)
      )
    }

    // ── 5. Alarmes ──────────────────────────────────────────────────────────
    if (alarme_lightsoft || alarme_vizee) {
      sections.push(
        new Table({
          width: { size: 100, type: WidthType.PERCENTAGE },
          borders: { top: BORDER_NONE, bottom: BORDER_NONE, left: BORDER_NONE, right: BORDER_NONE, insideH: BORDER_NONE, insideV: BORDER_NONE },
          rows: [
            bannerRow('ALARMES ACTIVES', 'B45309', 'FFFFFF', true, 19),
            ...(alarme_lightsoft ? [new TableRow({ children: [new TableCell({
              shading: { fill: 'FFFDE7', type: ShadingType.SOLID },
              borders: noBorder(),
              children: [para([run('Lightsoft: ', { bold: true, size: 18, color: '555555', font: 'Courier New' }), run(alarme_lightsoft, { size: 18, color: '1a1a1a', font: 'Courier New' })])]
            })] })] : []),
            ...(alarme_vizee ? [new TableRow({ children: [new TableCell({
              shading: { fill: 'FFFDE7', type: ShadingType.SOLID },
              borders: noBorder(),
              children: [para([run('Vizée:      ', { bold: true, size: 18, color: '555555', font: 'Courier New' }), run(alarme_vizee, { size: 18, color: '1a1a1a', font: 'Courier New' })])]
            })] })] : [])
          ]
        }),
        spacer(80)
      )
    }

    // ── 6. SOP procedures (grouped by phase) ────────────────────────────────
    if (sopsArr.length > 0) {
      sections.push(
        para(run('PROCÉDURES SOP', { bold: true, size: 24, color: NAVY, font: 'Segoe UI' }), {
          border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: NAVY } },
          spacing: { after: 160 }
        })
      )

      // Group by phase
      const phaseGroups = {}
      for (const s of sopsArr) {
        const ph = PHASE_MAP[s] || 2
        if (!phaseGroups[ph]) phaseGroups[ph] = []
        phaseGroups[ph].push(s)
      }

      for (const ph of Object.keys(phaseGroups).map(Number).sort()) {
        const phase = PHASES[ph]
        const pColor = phase ? phase.color : '2c5f8a'

        // Phase header
        sections.push(
          new Table({
            width: { size: 100, type: WidthType.PERCENTAGE },
            borders: { top: BORDER_NONE, bottom: BORDER_NONE, left: BORDER_NONE, right: BORDER_NONE, insideH: BORDER_NONE, insideV: BORDER_NONE },
            rows: [
              bannerRow('PHASE ' + ph + ' — ' + (phase ? phase.nom.toUpperCase() : ''), pColor, 'FFFFFF', true, 22),
              new TableRow({ children: [new TableCell({
                shading: { fill: 'F5F7FA', type: ShadingType.SOLID },
                borders: noBorder(),
                children: [para(run(phase ? phase.desc : '', { italic: true, size: 18, color: '555555', font: 'Segoe UI' }))]
              })] })
            ]
          }),
          spacer(60)
        )

        // Each SOP in phase
        for (const sopId of phaseGroups[ph]) {
          const sop = SOPS[sopId]
          if (!sop) continue

          const sopRows = [
            // SOP title row
            new TableRow({
              children: [new TableCell({
                shading: { fill: pColor, type: ShadingType.SOLID },
                borders: noBorder(),
                children: [para([
                  run(sopId + '  ', { bold: true, size: 20, color: 'FFFFFF', font: 'Segoe UI' }),
                  run(sop.nom, { bold: false, size: 20, color: 'DDDDDD', font: 'Segoe UI' })
                ])]
              })]
            }),
            // Ref row
            new TableRow({
              children: [new TableCell({
                shading: { fill: 'EEF2F7', type: ShadingType.SOLID },
                borders: noBorder(),
                children: [para(run(sop.ref, { size: 16, color: '666666', font: 'Courier New' }))]
              })]
            }),
            // Objectif row
            new TableRow({
              children: [new TableCell({
                shading: { fill: 'FFFFFF', type: ShadingType.SOLID },
                borders: { top: BORDER_NONE, bottom: { style: BorderStyle.SINGLE, size: 4, color: 'D0D8E8' }, left: { style: BorderStyle.SINGLE, size: 12, color: pColor }, right: BORDER_NONE },
                children: [para(run(sop.objectif, { italic: true, size: 18, color: '555555', font: 'Segoe UI' }))]
              })]
            })
          ]

          // Steps rows
          sop.steps.forEach((step, i) => {
            const [titre, ...rest] = step.split(' — ')
            const desc = rest.join(' — ')
            sopRows.push(new TableRow({
              children: [new TableCell({
                shading: { fill: i % 2 === 0 ? 'FFFFFF' : 'F9FAFB', type: ShadingType.SOLID },
                borders: { top: BORDER_NONE, bottom: { style: BorderStyle.SINGLE, size: 2, color: 'E8EDF4' }, left: { style: BorderStyle.SINGLE, size: 6, color: 'D0D8E8' }, right: BORDER_NONE },
                children: [para([
                  run('Étape ' + (i + 1) + ' — ', { bold: true, size: 18, color: pColor, font: 'Segoe UI' }),
                  run(titre, { bold: true, size: 18, color: '1a1a1a', font: 'Segoe UI' }),
                  ...(desc ? [run('\r' + desc, { size: 17, color: '444444', font: 'Segoe UI' })] : [])
                ])]
              })]
            }))
          })

          sections.push(
            new Table({
              width: { size: 100, type: WidthType.PERCENTAGE },
              borders: thinBorder('C8D4E8'),
              rows: sopRows
            }),
            spacer(100)
          )
        }
      }
    }

    // ── 7. Footer ───────────────────────────────────────────────────────────
    sections.push(
      new Table({
        width: { size: 100, type: WidthType.PERCENTAGE },
        borders: { top: { style: BorderStyle.SINGLE, size: 4, color: 'D0D8E8' }, bottom: BORDER_NONE, left: BORDER_NONE, right: BORDER_NONE, insideH: BORDER_NONE, insideV: BORDER_NONE },
        rows: [new TableRow({
          children: [
            new TableCell({
              borders: noBorder(),
              width: { size: 50, type: WidthType.PERCENTAGE },
              children: [para(run('OPSSD-03.03 — Service Technique NOC', { size: 16, color: '888888', font: 'Segoe UI' }))]
            }),
            new TableCell({
              borders: noBorder(),
              width: { size: 50, type: WidthType.PERCENTAGE },
              children: [para(run(docId + ' | ' + genTime, { size: 16, color: 'aaaaaa', font: 'Segoe UI' }), { alignment: AlignmentType.RIGHT })]
            })
          ]
        })]
      })
    )

    // ── Build document ──────────────────────────────────────────────────────
    const doc = new Document({
      sections: [{
        properties: {
          page: {
            size: { width: mm(210), height: mm(297) },
            margin: {
              top: mm(20), bottom: mm(20),
              left: mm(25), right: mm(20)
            }
          }
        },
        children: sections
      }]
    })

    const buf = await Packer.toBuffer(doc)
    res.setHeader('Content-Type', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    res.setHeader('Content-Disposition', `attachment; filename="${docId}.docx"`)
    res.send(buf)
  } catch (err) {
    console.error('[sop-to-docx]', err)
    res.status(500).json({ error: err.message })
  }
})

// ─── /convert/html-to-docx (pandoc, existing) ────────────────────────────────

app.post('/convert/html-to-docx', (req, res) => {
  const { html, reference_docx } = req.body
  if (!html) return res.status(400).json({ error: 'html field required' })

  const tmpDir  = fs.mkdtempSync(path.join(os.tmpdir(), 'pandoc-'))
  const inFile  = path.join(tmpDir, 'input.html')
  const outFile = path.join(tmpDir, 'output.docx')
  const refFile = reference_docx
    ? path.join(__dirname, 'reference', `${reference_docx}.docx`)
    : null

  fs.writeFileSync(inFile, html)
  const args = ['-f', 'html', '-t', 'docx', '-o', outFile, inFile]
  if (refFile && fs.existsSync(refFile)) args.push('--reference-doc', refFile)

  execFile('pandoc', args, (err) => {
    fs.unlinkSync(inFile)
    if (err) {
      fs.rmSync(tmpDir, { recursive: true })
      return res.status(500).json({ error: err.message })
    }
    res.setHeader('Content-Type',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    res.setHeader('Content-Disposition', 'attachment; filename="document.docx"')
    const stream = fs.createReadStream(outFile)
    stream.pipe(res)
    stream.on('end', () => fs.rmSync(tmpDir, { recursive: true }))
  })
})

app.get('/health', (_req, res) => res.json({ ok: true }))

app.listen(3001, () => console.log('[pandoc-api] ready on :3001'))
