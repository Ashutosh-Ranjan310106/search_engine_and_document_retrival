const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageBreak, LevelFormat
} = require('docx');
const fs = require('fs');

// Colors
const NAVY   = "1B3A6B";
const STEEL  = "2E5F8A";
const LGRAY  = "E8EDF3";
const MGRAY  = "F2F5F8";
const PGREEN = "D4EDDA";
const PYELL  = "FFF3CD";
const WHITE  = "FFFFFF";
const DARK   = "1A1A2E";
const GREEN_T = "155724";

const BORDER = { style: BorderStyle.SINGLE, size: 1, color: "ADBDCC" };
const BORDERS = { top: BORDER, bottom: BORDER, left: BORDER, right: BORDER };
const CM = { top: 80, bottom: 80, left: 120, right: 120 };

// ── helpers ──────────────────────────────────────────────────────────────────
function cell(text, opts = {}) {
  const fill = opts.fill || WHITE;
  return new TableCell({
    borders: BORDERS,
    width: opts.w ? { size: opts.w, type: WidthType.DXA } : undefined,
    shading: { fill, type: ShadingType.CLEAR },
    margins: CM,
    verticalAlign: VerticalAlign.CENTER,
    columnSpan: opts.span || 1,
    children: [new Paragraph({
      alignment: opts.ctr ? AlignmentType.CENTER : AlignmentType.LEFT,
      children: [new TextRun({
        text: String(text),
        font: "Arial", size: opts.sz || 18,
        bold: !!opts.bold, color: opts.tc || DARK
      })]
    })]
  });
}

function mcell(lines, opts = {}) {
  return new TableCell({
    borders: BORDERS,
    width: opts.w ? { size: opts.w, type: WidthType.DXA } : undefined,
    shading: { fill: opts.fill || WHITE, type: ShadingType.CLEAR },
    margins: CM,
    verticalAlign: VerticalAlign.TOP,
    children: lines.map(t => new Paragraph({
      spacing: { before: 30, after: 30 },
      children: [new TextRun({ text: String(t), font: "Arial", size: opts.sz || 18, color: DARK })]
    }))
  });
}

function hdrRow(cols, widths) {
  return new TableRow({
    tableHeader: true,
    children: cols.map((c, i) => cell(c, { w: widths[i], fill: NAVY, bold: true, tc: WHITE, sz: 18, ctr: true }))
  });
}

function dataRow(cols, widths, fill) {
  return new TableRow({
    children: cols.map((c, i) => cell(c, { w: widths[i], fill: fill || WHITE, sz: 17 }))
  });
}

function altRow(cols, widths, idx) {
  return dataRow(cols, widths, idx % 2 === 0 ? WHITE : MGRAY);
}

function passRow(cols, widths, idx) {
  const last = cols.length - 1;
  const status = cols[last];
  const fill = status === "PASS" ? PGREEN : status === "CLOSED" ? PGREEN : status === "N/A" ? MGRAY : PYELL;
  const tc = status === "PASS" || status === "CLOSED" ? GREEN_T : DARK;
  const rowFill = idx % 2 === 0 ? WHITE : MGRAY;
  return new TableRow({
    children: cols.map((c, i) => {
      if (i === last) return cell(c, { w: widths[i], fill, bold: true, tc, ctr: true, sz: 17 });
      return cell(c, { w: widths[i], fill: rowFill, sz: 17 });
    })
  });
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 160 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: STEEL, space: 4 } },
    children: [new TextRun({ text, font: "Arial", size: 32, bold: true, color: NAVY })]
  });
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 240, after: 100 },
    children: [new TextRun({ text, font: "Arial", size: 26, bold: true, color: STEEL })]
  });
}
function para(text, opts = {}) {
  return new Paragraph({
    spacing: { before: 60, after: 120 },
    alignment: opts.ctr ? AlignmentType.CENTER : AlignmentType.JUSTIFIED,
    children: [new TextRun({
      text, font: "Arial", size: opts.sz || 19,
      bold: !!opts.bold, color: opts.tc || DARK
    })]
  });
}
function sp() { return new Paragraph({ spacing: { before: 60, after: 60 }, children: [] }); }
function pb() { return new Paragraph({ children: [new PageBreak()] }); }
function bul(text) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { before: 40, after: 40 },
    children: [new TextRun({ text, font: "Arial", size: 19, color: DARK })]
  });
}
function tbl(rows, widths) {
  return new Table({
    width: { size: widths.reduce((a,b)=>a+b,0), type: WidthType.DXA },
    columnWidths: widths,
    rows
  });
}

// ── DOCUMENT ─────────────────────────────────────────────────────────────────
const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } } }]
    }]
  },
  styles: {
    default: { document: { run: { font: "Arial", size: 20, color: DARK } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: NAVY },
        paragraph: { spacing: { before: 360, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: STEEL },
        paragraph: { spacing: { before: 240, after: 100 }, outlineLevel: 1 } },
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: { top: 1200, right: 1080, bottom: 1080, left: 1260 }
      }
    },
    headers: {
      default: new Header({
        children: [
          new Paragraph({
            border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: STEEL, space: 4 } },
            spacing: { before: 0, after: 80 },
            children: [
              new TextRun({ text: "NEPTUNE MARITIME INDUSTRIES PTE. LTD.  |  ", font: "Arial", size: 16, bold: true, color: NAVY }),
              new TextRun({ text: "FAT Report — MV PACIFIC HORIZON  |  Doc: NMI-FAT-2025-0847  Rev 02", font: "Arial", size: 15, color: STEEL }),
            ]
          })
        ]
      })
    },
    footers: {
      default: new Footer({
        children: [
          new Paragraph({
            border: { top: { style: BorderStyle.SINGLE, size: 2, color: "ADBDCC", space: 4 } },
            spacing: { before: 80, after: 0 },
            children: [
              new TextRun({ text: "CONFIDENTIAL — Neptune Maritime Industries Pte. Ltd.  |  FAT Conducted: 14–16 October 2025  |  IMO: 9876543  |  Class: Lloyd's Register", font: "Arial", size: 14, color: "888888" })
            ]
          })
        ]
      })
    },

    children: [

      // ══════════════════ COVER PAGE ════════════════════════════════════
      new Paragraph({ spacing: { before: 800 }, children: [] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 80 },
        children: [new TextRun({ text: "NEPTUNE MARITIME INDUSTRIES PTE. LTD.", font: "Arial", size: 44, bold: true, color: NAVY })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 40 },
        children: [new TextRun({ text: "9 Tuas Basin Link, Singapore 638783  |  Tel: +65 6861 0088  |  www.neptunemaritme.sg", font: "Arial", size: 18, color: "555555" })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 320 },
        border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: NAVY, space: 8 } },
        children: [] }),

      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 },
        children: [new TextRun({ text: "FACTORY ACCEPTANCE TEST (FAT) REPORT", font: "Arial", size: 52, bold: true, color: NAVY })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 },
        children: [new TextRun({ text: "INTEGRATED BRIDGE NAVIGATION SYSTEM", font: "Arial", size: 36, bold: true, color: STEEL })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 240 },
        children: [new TextRun({ text: "MV PACIFIC HORIZON — IMO No. 9876543", font: "Arial", size: 26, color: "555555" })] }),

      tbl([
        new TableRow({ children: [cell("Document Number",{w:3200,fill:NAVY,bold:true,tc:WHITE}), cell("NMI-FAT-2025-0847",{w:5760,bold:true})] }),
        new TableRow({ children: [cell("Revision",{w:3200,fill:LGRAY,bold:true}), cell("02 — Final",{w:5760})] }),
        new TableRow({ children: [cell("Report Date",{w:3200,fill:NAVY,bold:true,tc:WHITE}), cell("22 October 2025",{w:5760})] }),
        new TableRow({ children: [cell("FAT Dates",{w:3200,fill:LGRAY,bold:true}), cell("14 October 2025 to 16 October 2025",{w:5760})] }),
        new TableRow({ children: [cell("Vessel Name",{w:3200,fill:NAVY,bold:true,tc:WHITE}), cell("MV PACIFIC HORIZON",{w:5760,bold:true})] }),
        new TableRow({ children: [cell("IMO Number",{w:3200,fill:LGRAY,bold:true}), cell("9876543",{w:5760})] }),
        new TableRow({ children: [cell("Vessel Type",{w:3200,fill:NAVY,bold:true,tc:WHITE}), cell("Bulk Carrier — 75,000 DWT (Handymax)",{w:5760})] }),
        new TableRow({ children: [cell("Flag State",{w:3200,fill:LGRAY,bold:true}), cell("Republic of the Marshall Islands",{w:5760})] }),
        new TableRow({ children: [cell("Shipowner / Operator",{w:3200,fill:NAVY,bold:true,tc:WHITE}), cell("Pacific Bulk Carriers Holding Ltd., Hong Kong",{w:5760})] }),
        new TableRow({ children: [cell("Shipyard",{w:3200,fill:LGRAY,bold:true}), cell("Hyundai Heavy Industries Co., Ltd. — Ulsan, South Korea",{w:5760})] }),
        new TableRow({ children: [cell("Hull Number",{w:3200,fill:NAVY,bold:true,tc:WHITE}), cell("HHI-2025-H3127",{w:5760})] }),
        new TableRow({ children: [cell("Classification Society",{w:3200,fill:LGRAY,bold:true}), cell("Lloyd's Register of Shipping (LR)",{w:5760})] }),
        new TableRow({ children: [cell("Equipment Supplier",{w:3200,fill:NAVY,bold:true,tc:WHITE}), cell("Neptune Maritime Industries Pte. Ltd., Singapore",{w:5760})] }),
        new TableRow({ children: [cell("Contract Reference",{w:3200,fill:LGRAY,bold:true}), cell("PBC-NMI-2025-CON-041 dated 15 March 2025",{w:5760})] }),
        new TableRow({ children: [cell("Overall FAT Result",{w:3200,fill:PGREEN,bold:true,tc:GREEN_T}), cell("PASS — APPROVED FOR SHIPMENT",{w:5760,fill:PGREEN,bold:true,tc:GREEN_T})] }),
      ], [3200,5760]),

      sp(), sp(),
      para("SIGNATURES — PREPARED, REVIEWED AND ACCEPTED BY:", { bold: true, tc: NAVY }),

      tbl([
        hdrRow(["ROLE","NAME / COMPANY / SIGNATURE","DATE SIGNED"],[3000,5000,1960]),
        new TableRow({ children: [cell("Prepared By (FAT Engineer)",{w:3000,fill:LGRAY,bold:true}), mcell(["Chua Wei Ming — Senior Test Engineer","Neptune Maritime Industries Pte. Ltd.","_______________________"],{w:5000}), cell("22 Oct 2025",{w:1960,ctr:true})] }),
        new TableRow({ children: [cell("Reviewed By (QC Manager)",{w:3000,fill:LGRAY,bold:true}), mcell(["Lim Boon Kiat — Quality Control Manager","Neptune Maritime Industries Pte. Ltd.","_______________________"],{w:5000}), cell("22 Oct 2025",{w:1960,ctr:true})] }),
        new TableRow({ children: [cell("Witnessed By (LR Surveyor)",{w:3000,fill:LGRAY,bold:true}), mcell(["Mr. James O'Connor — LR Surveyor","Lloyd's Register — Survey No. LR/SG/2025/0312","_______________________"],{w:5000}), cell("16 Oct 2025",{w:1960,ctr:true})] }),
        new TableRow({ children: [cell("Owner's Representative",{w:3000,fill:LGRAY,bold:true}), mcell(["Capt. (Ret.) Zhang Wei — Technical Superintendent","Pacific Bulk Carriers Holding Ltd.","_______________________"],{w:5000}), cell("16 Oct 2025",{w:1960,ctr:true})] }),
        new TableRow({ children: [cell("Flag State Inspector",{w:3000,fill:LGRAY,bold:true}), mcell(["Mr. David Lee — RMIS Authorized Inspector","Republic of Marshall Islands Ship Registry","_______________________"],{w:5000}), cell("16 Oct 2025",{w:1960,ctr:true})] }),
      ],[3000,5000,1960]),

      pb(),

      // ══════════════════ SECTION 1 ═════════════════════════════════════
      h1("1. INTRODUCTION AND SCOPE OF TEST"),
      h2("1.1 Purpose of This Report"),
      para("This Factory Acceptance Test (FAT) Report documents the testing, verification, and formal acceptance of the Integrated Bridge Navigation System (IBNS) supplied by Neptune Maritime Industries Pte. Ltd. (the 'Supplier') for fitment aboard MV PACIFIC HORIZON, a 75,000 DWT Handymax bulk carrier under construction at Hyundai Heavy Industries, Ulsan Shipyard, South Korea."),
      para("The FAT was conducted at the Supplier's facility at 9 Tuas Basin Link, Singapore 638783, from 14 to 16 October 2025. The purpose is to verify, in a controlled factory environment, that all navigation equipment supplied under Contract PBC-NMI-2025-CON-041 complies with agreed technical specifications, international conventions, IMO performance standards, classification society rules, and flag state requirements prior to shipment."),
      para("This report is prepared in accordance with Lloyd's Register Rules for the Classification of Ships (2025 Edition), IMO Resolution A.694(17), and project-specific FAT Procedure Document NMI-FAT-PROC-2025-0847."),

      h2("1.2 Background and Vessel Particulars"),
      para("MV PACIFIC HORIZON is being constructed for Pacific Bulk Carriers Holding Ltd. of Hong Kong. The vessel will trade worldwide carrying dry bulk commodities including iron ore, coal, grain, and fertilizers. As a vessel engaged in international voyages exceeding 3,000 GT, it is subject to the full requirements of SOLAS Chapter V (Safety of Navigation), SOLAS Chapter IV (Radiocommunications), and applicable IMO performance standards for shipborne navigational and radio communication equipment."),

      h2("1.3 Applicable Regulations and Standards"),
      tbl([
        hdrRow(["Reference","Title / Description","Applicable Equipment"],[2200,5600,2160]),
        ...[
          ["SOLAS V/Reg 19","Carriage requirements for shipborne navigational systems and equipment","All navigation equipment"],
          ["IMO Res. A.694(17)","General Requirements for Shipborne Radio Equipment forming Part of GMDSS","GMDSS, VHF, MF/HF"],
          ["IMO Res. MSC.192(79)","Revised Performance Standards for Radar Equipment","X-Band & S-Band Radar"],
          ["IMO Res. MSC.232(82)","Revised Performance Standards for ECDIS","ECDIS"],
          ["IMO Res. MSC.74(69) Annex 3","Recommendations on Performance Standards for AIS","AIS Class A Transponder"],
          ["IMO Res. MSC.116(73)","Performance Standards for Marine Transmitting Heading Devices (THDs)","Gyrocompass / FOG"],
          ["IEC 60945 Ed.4","Maritime Navigation and Radiocommunication Equipment — General Requirements","All equipment"],
          ["IEC 62388 Ed.2","Maritime Navigation and Radiocommunication Equipment — Shipborne Radar","X-Band & S-Band Radar"],
          ["IEC 62923 Ed.1","Bridge Alert Management (BAM) — Shipborne Systems","BAM / Integrated Bridge"],
          ["LR Rules Pt.5, Ch.2","Lloyd's Register Rules for Electrical and Electronic Equipment (2025)","All equipment"],
        ].map((r,i)=>altRow(r,[2200,5600,2160],i))
      ],[2200,5600,2160]),

      pb(),

      // ══════════════════ SECTION 2 ═════════════════════════════════════
      h1("2. PERSONNEL AND ATTENDANCE"),
      h2("2.1 FAT Team Composition"),
      para("The following personnel were present and actively participated in the FAT. All Neptune Maritime Industries test personnel hold valid competency certificates in the testing and commissioning of marine electronic systems. The Lloyd's Register Surveyor is an independent third-party witness. The Owner's Representative is authorized by Pacific Bulk Carriers Holding Ltd. to accept or reject equipment. The Flag State Representative from the Republic of Marshall Islands Ship Registry witnessed all SOLAS-mandatory tests."),
      tbl([
        hdrRow(["#","Name","Organization","Role","Days Present"],[500,2500,2500,3000,1460]),
        ...([
          ["1","Chua Wei Ming","Neptune Maritime Industries","Lead FAT Engineer","14–16 Oct"],
          ["2","Tan Ah Kow","Neptune Maritime Industries","Navigation Systems Technician","14–16 Oct"],
          ["3","Ravi Subramaniam","Neptune Maritime Industries","GMDSS / Comms Specialist","14–16 Oct"],
          ["4","Park Ji-Young","Neptune Maritime Industries","Software Integration Engineer","14–15 Oct"],
          ["5","Lim Boon Kiat","Neptune Maritime Industries (QC)","QC Manager / Reviewer","16 Oct"],
          ["6","Mr. James O'Connor","Lloyd's Register, Singapore","Class Surveyor (Witness)","14–16 Oct"],
          ["7","Capt. (Ret.) Zhang Wei","Pacific Bulk Carriers Holding Ltd.","Owner's Technical Representative","14–16 Oct"],
          ["8","Ms. Kim Su-Yeon","Hyundai Heavy Industries","Shipyard Representative","14–16 Oct"],
          ["9","Mr. David Lee","RMIS Flag State Authority","Flag State Authorized Inspector","15–16 Oct"],
          ["10","Mr. Anders Eriksson","Furuno Electric Co., Ltd.","OEM Technical Representative (Radar)","14–15 Oct"],
        ]).map((r,i)=>altRow(r,[500,2500,2500,3000,1460],i))
      ],[500,2500,2500,3000,1460]),

      pb(),

      // ══════════════════ SECTION 3 ═════════════════════════════════════
      h1("3. EQUIPMENT SCHEDULE AND IDENTIFICATION"),
      para("The following table identifies all equipment items within the scope of this FAT, together with serial numbers, software/firmware versions, and type approval references. Serial numbers were verified by physical inspection against equipment nameplates and Supplier's records. The LR Surveyor independently verified serial numbers on all SOLAS-mandatory equipment."),
      tbl([
        hdrRow(["#","Equipment Description","Manufacturer / Model","Serial Number","SW/FW","Type Approval","Result"],[400,3000,2200,2000,900,1500,960]),
        ...([
          ["1","X-Band Radar (Primary) 25 kW, IEC 62388","Furuno FAR-3230-BB","FAR3230-25-0841","SW 3.11.02","MED/4/0.2/0065","PASS"],
          ["2","S-Band Radar (Secondary) 30 kW, IEC 62388","Furuno FAR-3230S-BB","FAR3230S-30-0842","SW 3.11.02","MED/4/0.2/0066","PASS"],
          ["3","ECDIS (Primary) IMS S-63/S-57","JRC JAN-9201","JAN9201-P-0318","SW 4.02.01","MED/4/0.1/0210","PASS"],
          ["4","ECDIS (Backup) IMS S-63/S-57","JRC JAN-9201","JAN9201-B-0319","SW 4.02.01","MED/4/0.1/0210","PASS"],
          ["5","Fiber Optic Gyrocompass (FOG) — Master","Anschutz SmartPilot IIId","SP3D-FOG-8812","FW 2.07","MED/4/0.3/0011","PASS"],
          ["6","Gyrocompass Repeater (3 units)","Anschutz SmartPilot IIId","SP3D-REP-0041/2/3","FW 2.07","—","PASS"],
          ["7","AIS Class A Transponder","Saab R4 Transponder","R4AIS-2025-1092","SW 2.15.00","MED/4/0.2/0091","PASS"],
          ["8","GNSS / GPS Navigator (Primary)","Furuno GP-170","GP170-P-04411","SW 1.51","MED/4/0.3/0112","PASS"],
          ["9","GNSS / GPS Navigator (Backup)","Furuno GP-170","GP170-B-04412","SW 1.51","MED/4/0.3/0112","PASS"],
          ["10","Speed Log (Dual-Axis EM Log)","JRC JLN-900","JLN900-2025-0081","FW 3.01","MED/4/0.3/0048","PASS"],
          ["11","Echo Sounder (Single Beam)","JRC JFE-380","JFE380-2025-0099","FW 2.14","MED/4/0.3/0018","PASS"],
          ["12","VHF DSC Radio (Bridge) x2","Sailor SP3520-D","SP3520-0814/0815","SW 3.21","MED/4/0.4/0071","PASS"],
          ["13","INMARSAT-C (GMDSS) + EGC","Sailor 6110 Mini-C","S6110-2025-0293","SW 5.02.01","MED/4/0.4/0022","PASS"],
          ["14","MF/HF SSB Radio + DSC","Sailor SP3525 MF/HF","SP3525-2025-0401","SW 2.10","MED/4/0.4/0101","PASS"],
          ["15","SART Radar Transponder x2","McMurdo S20 SART","S20-0081/0082","—","MED/4/0.4/0033","PASS"],
          ["16","AIS-SART MOB Device x2","Ocean Signal rescueME AIS1","AIS1-1104/1105","—","MED/4/0.4/0177","PASS"],
          ["17","NAVTEX Receiver","Furuno NX-700A","NX700A-2025-0302","SW 2.01","MED/4/0.4/0088","PASS"],
          ["18","Bridge Alert Management (BAM)","Neptune Maritime NAVIGATOR-X","NAVX-2025-0088","SW 1.08.03","LR/TA/2024/1198","PASS"],
          ["19","Voyage Data Recorder (VDR)","Furuno VR-7000","VR7000-2025-0518","SW 3.09.00","MED/4/0.1/0193","PASS"],
          ["20","Autopilot System","Anschutz NautiPilot 5000","NP5000-2025-0209","SW 4.11","MED/4/0.2/0015","PASS"],
        ]).map((r,i)=>passRow(r,[400,3000,2200,2000,900,1500,960],i))
      ],[400,3000,2200,2000,900,1500,960]),

      pb(),

      // ══════════════════ SECTION 4 ═════════════════════════════════════
      h1("4. X-BAND AND S-BAND RADAR SYSTEMS"),
      h2("4.1 Equipment Description and Technical Specifications"),
      para("The vessel is fitted with a primary 25 kW X-Band radar (9.3 GHz) and a secondary 30 kW S-Band radar (3.0 GHz), both manufactured by Furuno Electric Co., Ltd. Both systems carry EU MED Wheelmark type approval and comply with IMO Resolution MSC.192(79) and IEC 62388:2013 Ed.2. The X-Band radar is the primary system used for close-range target detection, collision avoidance, and port approach navigation. The S-Band provides superior performance in precipitation and sea clutter. Both radars are equipped with ARPA functionality capable of auto-acquiring and tracking a minimum of 100 targets simultaneously with continuous CPA/TCPA computation and collision alarms."),

      tbl([
        hdrRow(["Parameter","X-Band Radar (FAR-3230-BB)","S-Band Radar (FAR-3230S-BB)"],[3200,3200,3560]),
        ...([
          ["Frequency Band","9.3 GHz (X-Band, 3 cm)","3.0 GHz (S-Band, 10 cm)"],
          ["Peak Transmit Power","25 kW","30 kW"],
          ["Antenna Rotation Speed","24 / 42 RPM (selectable)","24 / 42 RPM (selectable)"],
          ["Antenna Beam Width (Horizontal)","1.23 deg @ 6.5 ft antenna","2.25 deg @ 8 ft antenna"],
          ["Maximum Range","96 nautical miles","96 nautical miles"],
          ["Minimum Range","Less than 25 m","Less than 25 m"],
          ["Range Accuracy","Less than 1% of range scale or 30 m","Less than 1% of range scale or 30 m"],
          ["Bearing Accuracy","Within +/-1 deg","Within +/-1 deg"],
          ["ARPA Target Capacity","100 auto + 20 manual","100 auto + 20 manual"],
          ["Display Size","19-inch SXGA LCD","19-inch SXGA LCD"],
          ["Operating Temperature","-15 deg C to +55 deg C","-15 deg C to +55 deg C"],
        ]).map((r,i)=>new TableRow({ children:[
          cell(r[0],{w:3200,fill:LGRAY,bold:true,sz:17}),
          cell(r[1],{w:3200,fill:i%2===0?WHITE:MGRAY,sz:17}),
          cell(r[2],{w:3560,fill:i%2===0?WHITE:MGRAY,sz:17}),
        ]}))
      ],[3200,3200,3560]),

      sp(),
      h2("4.2 Visual and Physical Inspection"),
      tbl([
        hdrRow(["Inspection Item","Observations / Findings","Ref. Clause","Result"],[2500,4800,1000,1660]),
        ...([
          ["Antenna Scanner (X-Band)","Scanner rotates freely. No physical damage. All fasteners secure. Cable entry sealed. Excellent condition.","IEC 62388 §4.1","PASS"],
          ["Antenna Scanner (S-Band)","Scanner rotates freely. No physical damage. Bearing condition good. Cable entry sealed.","IEC 62388 §4.1","PASS"],
          ["Transceiver Unit (X-Band)","All panels intact. No dents or corrosion. Ventilation grilles clear. Magnetron reads 000002 hrs.","IEC 62388 §4.2","PASS"],
          ["Transceiver Unit (S-Band)","All panels intact. Minor cosmetic scratch on lower panel — noted and accepted by Owner's Rep (see NCR-001). Magnetron reads 000004 hrs.","IEC 62388 §4.2","PASS"],
          ["Display Units (both)","Both displays free of scratches. Daylight readable. All controls operational. Labels legible.","IEC 62388 §5.1","PASS"],
          ["Nameplate Verification","All nameplates legible. Serial numbers match FAT documentation exactly.","LR Rules","PASS"],
          ["Cable and Connector Inspection","All coaxial antenna cables intact, correctly terminated, watertight glands fitted. No chafing.","IEC 60945 §9","PASS"],
          ["Earth Bonding","Earth bonding cables fitted to all units, correctly sized. Continuity confirmed with test meter.","IEC 60945 §9","PASS"],
        ]).map((r,i)=>passRow(r,[2500,4800,1000,1660],i))
      ],[2500,4800,1000,1660]),

      sp(),
      h2("4.3 Performance Tests — X-Band Radar (Furuno FAR-3230-BB)"),
      para("Performance testing was conducted using calibrated test equipment including a Radar Performance Monitor (RPM) and signal generator. Tests were performed to verify compliance with IMO MSC.192(79) and IEC 62388 Ed.2. The Furuno OEM representative Mr. Anders Eriksson was present throughout and confirmed manufacturer-specific test parameters."),
      tbl([
        hdrRow(["Test Description","Acceptance Criterion","Measured Result","Clause","Result"],[3000,2600,2000,1000,1360]),
        ...([
          ["Transmitter Power Output","22 kW minimum (spec 25 kW)","24.7 kW measured","IEC 62388 §7.3","PASS"],
          ["Minimum Range (Target Detection)","Less than 25 m with 10 m2 RCS target","15 m measured","MSC.192 §2.3","PASS"],
          ["Range Accuracy (3 nm scale)","1% or 30 m (whichever greater)","±18 m at 2.5 nm","IEC 62388 §7.8","PASS"],
          ["Bearing Accuracy","Within ±1 deg of true bearing","±0.5 deg measured (0.9 deg worst case)","IEC 62388 §7.9","PASS"],
          ["Range Discrimination","30 m or less between two targets","22 m measured","MSC.192 §2.5","PASS"],
          ["Bearing Discrimination","2.5 deg or less between two targets","1.8 deg measured","MSC.192 §2.5","PASS"],
          ["Sea Clutter (STC) Control","Suppresses clutter; targets retained","Sea clutter suppressed; test target at 0.3 nm retained","IEC 62388 §9.5","PASS"],
          ["Rain Clutter (FTC) Control","Suppresses rain clutter; targets retained","Rain clutter suppressed; 1 nm target retained","IEC 62388 §9.5","PASS"],
          ["North-Up Stabilized Mode","Heading data accepted; display rotates correctly","N-Up mode confirmed with FOG heading input","MSC.192 §5.2","PASS"],
          ["True Motion Mode","Position tracking with speed/heading input","TM mode confirmed; own ship trail correct","MSC.192 §5.2","PASS"],
          ["VRM Accuracy (two VRMs)","1% full scale accuracy","VRM1: ±0.05 nm, VRM2: ±0.04 nm","IEC 62388 §9.10","PASS"],
          ["EBL Accuracy (two EBLs)","0.5 deg accuracy","EBL1: ±0.3 deg, EBL2: ±0.4 deg","IEC 62388 §9.10","PASS"],
          ["Parallel Index Lines","PI lines operational","PI lines displayed and offset correctly","MSC.191 §7","PASS"],
        ]).map((r,i)=>passRow(r,[3000,2600,2000,1000,1360],i))
      ],[3000,2600,2000,1000,1360]),

      sp(),
      h2("4.4 ARPA Target Tracking Tests"),
      para("ARPA functionality was tested using the Furuno integrated ARPA simulator mode, which injects synthetic target data into the radar display at known positions, speeds, and courses. This allows verification of CPA/TCPA computation accuracy, alarm functions, and tracking performance. The ARPA simulator is approved for FAT testing by Furuno Electric and was verified against OEM reference data."),
      tbl([
        hdrRow(["ARPA Test Description","Acceptance Criterion","Test Result","Clause","Result"],[3200,2600,2000,1000,1160]),
        ...([
          ["Target Acquisition — Auto Mode","100 auto targets; acquisition within 3 sweeps","100 targets acquired; avg. acquisition in 2.1 sweeps","MSC.192 §4.2","PASS"],
          ["Target Acquisition — Manual Mode","20 manual targets in addition to auto","20 manual targets confirmed alongside 100 auto","MSC.192 §4.2","PASS"],
          ["CPA / TCPA Computation Accuracy","CPA error 0.3 nm or less; TCPA 0.5 min after steady state","CPA error: 0.15 nm; TCPA: 0.2 min after 3 min","MSC.192 §4.5","PASS"],
          ["Collision Alarm (CPA/TCPA)","Audible and visual alarm at threshold","Alarm at CPA 0.5 nm / TCPA 6 min — both alarms confirmed","MSC.192 §4.6","PASS"],
          ["Lost Target Alarm","Alarm within 3 sweeps of target loss","Lost target alarm at 2 sweeps","MSC.192 §4.7","PASS"],
          ["Vector Display (True / Relative)","Correct vector in both modes","Both modes confirmed; correct agreement with course and speed","MSC.192 §4.4","PASS"],
          ["History Trail (3 and 6 min)","Trail in both 3-min and 6-min settings","Trails displayed correctly in both settings","MSC.192 §4.4","PASS"],
          ["Guardzones (Two Independent)","Alarm on target entry into guardzone","Both guardzones triggered correctly with simulated target entry","MSC.192 §4.9","PASS"],
          ["Target Recovery After Manoeuvre","Re-tracks within 1 min after 90-deg turn","Recovery confirmed at 41 seconds after simulated 90-deg turn","MSC.192 §4.8","PASS"],
        ]).map((r,i)=>passRow(r,[3200,2600,2000,1000,1160],i))
      ],[3200,2600,2000,1000,1160]),

      pb(),

      // ══════════════════ SECTION 5 ═════════════════════════════════════
      h1("5. ELECTRONIC CHART DISPLAY AND INFORMATION SYSTEM (ECDIS)"),
      h2("5.1 Equipment Description"),
      para("Two ECDIS units are supplied — primary and backup — both JRC JAN-9201 units with software version 4.02.01. Both carry EU MED Wheelmark type approval MED/4/0.1/0.0210 and comply with IMO Resolution MSC.232(82) and IHO publications S-52, S-57 Ed.3.1, and S-63 Ed.1.2. The ECDIS units serve as the primary means of navigation replacing mandatory paper charts per SOLAS Reg. V/19.2.10."),
      para("Each ECDIS is connected to primary and backup GPS/GNSS sensors, the FOG gyrocompass, the dual-axis speed log, and the AIS transponder via IEC 61162-1 (NMEA 0183) interfaces. The backup ECDIS operates entirely independently from the primary, maintaining its own sensor connections to prevent common-mode failure. This independence was specifically tested and witnessed by the LR Surveyor."),
      h2("5.2 ECDIS Performance and Functional Tests"),
      tbl([
        hdrRow(["Test Description","Acceptance Criterion","Observed Result","Clause","Result"],[2800,2800,2500,900,960]),
        ...([
          ["ENC Display — Base Display","Correct base elements per S-52 displayed","Coastlines, safe depth contour, isolated dangers, prohibited areas all displayed correctly","S-52 §3","PASS"],
          ["ENC Display — Standard Display","Additional chart elements per S-52 standard","Standard display confirmed with all additional layers active","S-52 §3","PASS"],
          ["Safe Contour Setting","Configurable safety contour; unsafe depths highlighted","Safety contour set to 10 m; unsafe areas highlighted in blue. Danger highlight correct.","MSC.232 §6.1","PASS"],
          ["Own Ship Position Display","GPS position continuously updated on chart","Position updating every 1 second from primary GPS. XTD visible on chart.","MSC.232 §5.1","PASS"],
          ["GPS/GNSS Sensor Switchover","Backup GPS auto-selects if primary fails; alarm generated","Primary GPS disconnected — backup selected within 3 sec; alarm generated. Confirmed by LR Surveyor.","MSC.232 §10.2","PASS"],
          ["Route Planning Function","Waypoints, track, distance, ETA computed correctly","Route planned Singapore to Rotterdam (18 waypoints); distance, ETE and ETA correct vs. manual calculation.","MSC.232 §5.3","PASS"],
          ["Route Monitoring — Anti-Grounding","Anti-grounding alarm at configurable look-ahead distance","Alarm triggered at 3 nm look-ahead; hazard highlighted on chart.","MSC.232 §9.3","PASS"],
          ["Waypoint Approach Alarm","Alarm at configurable distance before waypoint","Alarm at 1.0 nm before waypoint as configured; audible and visual alarms confirmed.","MSC.232 §9.3","PASS"],
          ["XTD (Cross-Track Distance) Alarm","Alarm when vessel deviates beyond set XTD limit","XTD alarm at 0.2 nm deviation as set. Alert passed to BAM system.","MSC.232 §9.3","PASS"],
          ["Speed/Heading from FOG and Log","Heading from gyro and speed from log displayed","Heading and speed displayed correctly; confirmed match with sensor readings.","MSC.232 §5.2","PASS"],
          ["AIS Targets on ECDIS","AIS targets overlaid with correct symbology","AIS targets displayed with correct IHO S-52 symbology; target data popup correct.","MSC.232 §5.4","PASS"],
          ["Radar Overlay on ECDIS","Radar echo overlay functional","Radar overlay from X-Band radar displayed correctly; matches chart features.","MSC.232 §5.5","PASS"],
          ["S-63 Chart Permit Verification","Valid permits accepted; expired permits rejected","Valid permits accepted; expired permit correctly rejected with error message.","S-63 §4","PASS"],
          ["Chart Update Application","ENC updates applied; update records maintained","Test update applied; history log correct.","S-52 §8","PASS"],
          ["Night Mode / Dusk Mode Display","Display brightness adjustable; night colour scheme operational","All display modes (Day, Dusk, Night) correct; minimum brightness meets requirements.","IEC 60945 §6","PASS"],
          ["Backup ECDIS Independence Test","Backup ECDIS operates independently of primary","Primary ECDIS powered off; Backup continued normal operation using own sensor inputs without interruption. LR Surveyor confirmed.","MSC.232 §3.3","PASS"],
        ]).map((r,i)=>passRow(r,[2800,2800,2500,900,960],i))
      ],[2800,2800,2500,900,960]),

      pb(),

      // ══════════════════ SECTION 6 ═════════════════════════════════════
      h1("6. GYROCOMPASS, GNSS AND AIS SENSORS"),
      h2("6.1 Fiber Optic Gyrocompass (FOG) — Anschutz SmartPilot IIId"),
      para("The Anschutz SmartPilot IIId uses interferometric fiber optic technology to measure angular rate and derive heading. Unlike conventional mechanical gyrocompasses, the FOG contains no rotating mechanical parts, eliminating lubrication requirements and significantly reducing maintenance demands. The system achieves heading accuracy of ±0.1 deg (1 sigma) in static conditions and better than ±0.5 deg under dynamic vessel motion. It feeds heading data to all connected bridge equipment via NMEA 0183 HDT/HDG sentences at 10 Hz and provides an analog synchro output for three repeater compass units at the conning position, port bridge wing, and starboard bridge wing."),
      tbl([
        hdrRow(["Test Description","Acceptance Criterion","Measured Result","Ref.","Result"],[3000,2800,2000,900,1260]),
        ...([
          ["Start-Up Time from Cold Start","Heading output within 5 minutes","Heading available at 3 min 42 sec (cold start)","MSC.116(73) §3","PASS"],
          ["Heading Accuracy — Static","±0.5 deg (1 sigma) corrected for latitude","±0.08 deg (1 sigma) over 10 minutes static","MSC.116(73) §4.1","PASS"],
          ["Heading Repeatability","±0.25 deg or less over 30-minute period","±0.06 deg measured over 30 minutes — excellent stability","MSC.116(73) §4.2","PASS"],
          ["Rate of Turn Output","ROT within ±1 deg/min accuracy","ROT output correct; ±0.4 deg/min accuracy confirmed","IEC 62882 §5","PASS"],
          ["Synchro Output (Repeater Drive)","3 repeaters within ±0.5 deg of master","All 3 repeaters confirmed within ±0.3 deg of master","MSC.116(73) §5","PASS"],
          ["NMEA HDT/HDG Sentence Output","Correct sentences at 10 Hz update rate","HDT and HDG confirmed at 10 Hz; data correct","IEC 61162-1","PASS"],
          ["Power Supply Interruption Recovery","Heading reacquired within 60 seconds","Heading reacquired at 58 sec after 30-sec power interruption","MSC.116(73) §6","PASS"],
        ]).map((r,i)=>passRow(r,[3000,2800,2000,900,1260],i))
      ],[3000,2800,2000,900,1260]),

      sp(),
      h2("6.2 GNSS / GPS Navigation System — Furuno GP-170"),
      para("Two independent GNSS receiver units are installed — Primary GPS and Backup GPS. Both units receive signals from GPS (US), GLONASS (Russia), and SBAS constellations. The antennas are positioned at separate locations on the vessel to eliminate the possibility of a single obstruction affecting both receivers. Each unit outputs position data in NMEA 0183 GGA, GLL, RMC, VTG, and ZDA sentences to all connected navigation equipment."),
      tbl([
        hdrRow(["Test Description","Acceptance Criterion","Measured Result","Ref.","Result"],[3000,2800,2000,900,1260]),
        ...([
          ["Position Accuracy (open sky, survey point)","CEP 10 m (GPS only); 5 m (SBAS)","CEP 2.3 m (SBAS-aided, 100 measurements over 30 min)","IMO Res. A.915","PASS"],
          ["NMEA GGA Sentence Output","GGA at 1 Hz; position correct","GGA at 1 Hz; position confirmed against DGPS reference","IEC 61162-1","PASS"],
          ["NMEA ZDA Sentence Output","ZDA (time/date) at 1 Hz","UTC time correct; date confirmed","IEC 61162-1","PASS"],
          ["Primary to Backup Switchover","Auto-switchover within 5 seconds; alarm generated","Switchover at 2.8 seconds; alarm confirmed on DDU and ECDIS","MSC.232 §10.2","PASS"],
          ["Position Jump Alarm","Alarm if position changes more than 1 nm instantaneously","Alarm triggered correctly when simulated 2 nm position jump injected","MSC.232 §10.3","PASS"],
        ]).map((r,i)=>passRow(r,[3000,2800,2000,900,1260],i))
      ],[3000,2800,2000,900,1260]),

      sp(),
      h2("6.3 AIS Class A Transponder — Saab R4"),
      para("The Saab R4 AIS Class A Transponder complies with IMO Resolution MSC.74(69) Annex 3, ITU-R M.1371-5, and IEC 62287-1. The system automatically broadcasts vessel static data (MMSI: 538009187, IMO: 9876543, Name: PACIFIC HORIZON, Type: 70 Cargo, Dims: 229x32 m), dynamic data (position, SOG, COG, heading, ROT, navigational status), and voyage-related data at intervals per SOTDMA protocol."),
      tbl([
        hdrRow(["Test Description","Acceptance Criterion","Observed Result","Ref.","Result"],[3000,2800,2000,900,1260]),
        ...([
          ["Static Data Programming and Display","All static data correctly programmed and transmitted","MMSI, IMO, Name, Type, Dims all confirmed correct in AIS Message Type 1","IEC 62287-1 §6","PASS"],
          ["Dynamic Data Transmission Rate","Reporting rate per ITU M.1371 (10s at speed above 14 kts)","10-second rate confirmed at simulated 15 kt speed","ITU M.1371 §3.3","PASS"],
          ["Position Accuracy in AIS Message","Position from GNSS within AIS; RAIM status indicated","GPS position in Msg Type 1 confirmed correct; RAIM status = 1 (normal)","IEC 62287-1 §8.3","PASS"],
          ["Heading from Gyrocompass in AIS","True heading from FOG transmitted in AIS message","Heading 045.0 deg (simulated) confirmed in AIS Message Type 1","IEC 62287-1 §8.3","PASS"],
          ["Target Display — Receive Mode","AIS targets received and displayed on MKD and ECDIS","3 simulated AIS targets confirmed on MKD and ECDIS with correct symbols","IEC 62288 §5","PASS"],
          ["Silent Mode (VHF Off)","AIS silenced per Master's authority; alarm generated","Silent mode activated; alarm generated on BAM system","SOLAS V/19.2.4","PASS"],
          ["Channel Management","CH 87B and 88B default; regional channel change accepted","Default channels confirmed; channel change via MKD tested successfully","ITU M.1371 §4.2","PASS"],
        ]).map((r,i)=>passRow(r,[3000,2800,2000,900,1260],i))
      ],[3000,2800,2000,900,1260]),

      pb(),

      // ══════════════════ SECTION 7 ═════════════════════════════════════
      h1("7. GLOBAL MARITIME DISTRESS AND SAFETY SYSTEM (GMDSS)"),
      h2("7.1 GMDSS Equipment Suite Overview"),
      para("MV PACIFIC HORIZON operates worldwide in GMDSS Sea Areas A1, A2, A3, and A4 (polar areas). The vessel carries a full GMDSS equipment suite as mandated by SOLAS Chapter IV. The EPIRB (406 MHz) is supplied under a separate contract and is excluded from this FAT scope."),
      tbl([
        hdrRow(["#","Equipment","GMDSS Function","Sea Area","SOLAS Req.","Result"],[400,3200,2500,900,1500,1460]),
        ...([
          ["1","VHF DSC Controller x2 (Sailor SP3520-D)","Distress alerting, Ship-to-ship communications","A1","SOLAS IV/7.1.1","PASS"],
          ["2","MF/HF SSB + DSC (Sailor SP3525)","Distress alerting, Long range communications","A2, A3, A4","SOLAS IV/9.1","PASS"],
          ["3","INMARSAT-C + EGC (Sailor 6110 Mini-C)","Ship-earth station, MSI reception","A3, A4","SOLAS IV/10.1.1","PASS"],
          ["4","NAVTEX Receiver (Furuno NX-700A)","MSI — NavWarnings, weather, SAR","A1, A2","SOLAS IV/7.1.2","PASS"],
          ["5","SART Radar Transponder x2 (McMurdo S20)","Location of survival craft by radar","All areas","SOLAS IV/7.1.3","PASS"],
          ["6","AIS-SART MOB Device x2 (Ocean Signal AIS1)","Location of person in distress via AIS","All areas","MSC.1/Circ.1515","PASS"],
          ["7","406 MHz EPIRB x1 (separate supply)","Satellite distress alerting","All areas","SOLAS IV/7.1.6","N/A"],
        ]).map((r,i)=>passRow(r,[400,3200,2500,900,1500,1460],i))
      ],[400,3200,2500,900,1500,1460]),

      sp(),
      h2("7.2 VHF DSC Radio Tests — Sailor SP3520-D"),
      tbl([
        hdrRow(["Test Description","Acceptance Criterion","Observed Result","Ref.","Result"],[2800,2600,2400,900,1260]),
        ...([
          ["DSC Distress Alert Transmission (Internal)","DSC alert generated on CH70; correct MMSI transmitted","Alert in internal test mode; MMSI correct; self-check passed","SOLAS IV/7.1.1","PASS"],
          ["Transmit Power — 25W and 1W","25W and 1W selectable; within ±30% of rated","25W: 23.1W measured; 1W: 1.05W measured — both within tolerance","IEC 60945 §8","PASS"],
          ["Receiver Sensitivity CH16","Less than -107 dBm for 12 dB SINAD","-108.5 dBm measured — satisfactory","ITU-R M.489","PASS"],
          ["Interoperability — Unit 1 to Unit 2","Units communicate on CH16 and working channels","Clear communications on CH16 and CH06 in conference call test","SOLAS IV","PASS"],
          ["Scanning Function (Priority Scan)","CH16 in priority scan; alarm on CH16 call","Priority scan confirmed; audible alarm on CH16 call from Unit 2","IEC 62287-3","PASS"],
          ["Remote Handset (Bridge Wings)","Handsets at both bridge wings operational","Both port and starboard handsets operational on both VHF units","MSC.1/Circ.","PASS"],
        ]).map((r,i)=>passRow(r,[2800,2600,2400,900,1260],i))
      ],[2800,2600,2400,900,1260]),

      pb(),

      // ══════════════════ SECTION 8 ═════════════════════════════════════
      h1("8. VOYAGE DATA RECORDER (VDR) AND BRIDGE ALERT MANAGEMENT"),
      h2("8.1 Voyage Data Recorder — Furuno VR-7000"),
      para("The Furuno VR-7000 is a full VDR complying with IMO Resolution MSC.333(90) and IEC 61996-1 Ed.2. Though a Simplified VDR (S-VDR) would be permissible for this vessel type per SOLAS V/20, the Owner has specified a full VDR for maximum recording capability. Data recorded includes bridge audio (all microphones), radar video from both radars, ECDIS screenshots, AIS data, GPS position and time, heading, speed, depth, wind, rudder angle, engine telegraph, thruster status, watertight and fire door status, and VHF radio communications. All data is stored in a 12-hour rolling loop on a certified float-free capsule rated to 6,000 m depth."),
      tbl([
        hdrRow(["Test Description","Acceptance Criterion","Observed Result","Clause","Result"],[2800,2600,2400,900,1260]),
        ...([
          ["Data Input — GPS Position (GGA)","Position recorded at 1-second interval or less","1-second recording confirmed by playback","IEC 61996-1 §7.5","PASS"],
          ["Data Input — Heading (HDT)","Heading at 1-second interval or less","1-second recording; heading from FOG correct","IEC 61996-1 §7.5","PASS"],
          ["Data Input — Speed (VBW/VHW)","Speed from speed log recorded","STW from EM log recorded correctly; playback confirmed","IEC 61996-1 §7.5","PASS"],
          ["Data Input — Radar Video (X-Band)","Radar image recorded every 15 seconds","Image at 15-sec intervals confirmed; playback correct","IEC 61996-1 §7.6","PASS"],
          ["Data Input — AIS NMEA Data","AIS messages recorded","VDM/VDO sentences recorded; playback shows correct targets","IEC 61996-1 §7.5","PASS"],
          ["Bridge Audio Recording","All bridge mics recorded; voice intelligible","4 microphone channels confirmed; voice intelligible on playback","IEC 61996-1 §7.4","PASS"],
          ["VHF Communications Recording","VHF radio audio from both units recorded","Both VHF channels confirmed; playback intelligible","IEC 61996-1 §7.4","PASS"],
          ["Capsule Status and Self-Check","VDR passes self-check; no fault indications","Self-check completed without fault; float-free mechanism operational","IEC 61996-1 §9","PASS"],
          ["Time Synchronisation","VDR time synchronised to GPS UTC","VDR clock synchronised to GPS UTC; offset 0.0 seconds","IEC 61996-1 §7.5","PASS"],
        ]).map((r,i)=>passRow(r,[2800,2600,2400,900,1260],i))
      ],[2800,2600,2400,900,1260]),

      sp(),
      h2("8.2 Bridge Alert Management (BAM) — Neptune Maritime NAVIGATOR-X"),
      para("The Neptune Maritime NAVIGATOR-X BAM System complies with IEC 62923-1 Ed.1 and IEC 62923-2 Ed.1. The BAM receives alert inputs from all connected bridge equipment and presents them on a unified alert management workstation. Alerts are prioritised into three categories (Alarm, Warning, Caution) and acknowledgement is managed in accordance with IEC 62923 requirements."),
      tbl([
        hdrRow(["Test Description","Acceptance Criterion","Observed Result","Ref.","Result"],[2800,2600,2400,900,1260]),
        ...([
          ["Alert Reception from ECDIS (XTD Alarm)","ECDIS XTD alarm displayed on BAM","XTD alarm received and displayed on BAM within 1 second","IEC 62923-1 §4.2","PASS"],
          ["Alert Reception from ARPA (CPA Alarm)","Radar CPA alarm received on BAM","CPA alarm displayed on BAM; alert category: Alarm","IEC 62923-1 §4.2","PASS"],
          ["Alert Escalation (Unacknowledged)","Re-alerted after 30 sec if unacknowledged","Re-alert at 30-sec intervals until acknowledged; audible alarm re-triggered","IEC 62923-1 §5.3","PASS"],
          ["Acknowledgement Function","Alerts acknowledged from BAM workstation","Acknowledgement confirmed; alerts move to acknowledged list","IEC 62923-1 §5.4","PASS"],
          ["Inhibit Function (Caution Class)","Caution-class alerts can be inhibited","Inhibit confirmed for caution-class only; alarm-class cannot be inhibited","IEC 62923-1 §5.5","PASS"],
          ["Alert Transfer (Watchkeeping Handover)","Responsibility transferable between stations","Alert responsibility transferred; confirmed on both stations","IEC 62923-2 §4","PASS"],
        ]).map((r,i)=>passRow(r,[2800,2600,2400,900,1260],i))
      ],[2800,2600,2400,900,1260]),

      pb(),

      // ══════════════════ SECTION 9 ═════════════════════════════════════
      h1("9. SYSTEM INTEGRATION AND INTERFACE TESTS"),
      para("Integration testing verifies correct data transfer between all bridge equipment via NMEA 0183 and proprietary data bus interfaces. All inter-equipment interfaces are routed through the Neptune Maritime Industries Data Distribution Unit (DDU) Model NMI-DDU-02, which provides signal isolation, buffering, and priority-based automatic switchover. Tests were conducted with all equipment powered simultaneously to replicate actual bridge operating conditions."),
      tbl([
        hdrRow(["#","Data Source","Recipient","Data Type","Test Observation","Clause","Result"],[400,1800,1800,1600,2800,1000,1160]),
        ...([
          ["1","FOG Gyrocompass","ECDIS (Primary)","NMEA HDT @10Hz","Heading on ECDIS matches gyro exactly","IEC 61162-1","PASS"],
          ["2","FOG Gyrocompass","X-Band Radar","NMEA HDT @10Hz","Radar N-Up mode correct; heading matches gyro","IEC 61162-1","PASS"],
          ["3","FOG Gyrocompass","AIS Transponder","NMEA HDT @1Hz","AIS Msg 1 heading field matches gyro","IEC 61162-1","PASS"],
          ["4","FOG Gyrocompass","Autopilot","NMEA HDT @10Hz","Autopilot receives heading; confirmed by display","IEC 61162-1","PASS"],
          ["5","Primary GNSS","ECDIS (Primary)","NMEA GGA @1Hz","Position on ECDIS matches GPS; 1-sec update","IEC 61162-1","PASS"],
          ["6","Primary GNSS","AIS Transponder","NMEA GGA @1Hz","AIS position = GPS position; confirmed correct","IEC 61162-1","PASS"],
          ["7","Primary GNSS","VDR","NMEA GGA @1Hz","Position logged at 1-sec intervals; playback correct","IEC 61162-1","PASS"],
          ["8","Speed Log (EM Log)","ECDIS (Primary)","NMEA VBW @1Hz","STW displayed on ECDIS; confirmed correct","IEC 61162-1","PASS"],
          ["9","AIS Transponder","ECDIS (Primary)","NMEA VDM (var.)","AIS targets on ECDIS with correct symbology","IEC 61162-1","PASS"],
          ["10","AIS Transponder","X-Band Radar","NMEA VDM (var.)","AIS targets in radar overlay; symbols correct","IEC 61162-1","PASS"],
          ["11","ECDIS (Primary)","BAM System","IEC 62923 CAN","ECDIS alarms transmitted to BAM; all categories correct","IEC 62923","PASS"],
          ["12","DDU Sensor Switchover","ECDIS/Radar/AIS","Automatic","Primary GPS and Gyro failure simulated; DDU switched to backup within 3 sec; alarm generated on all connected displays","NMI DDU Spec","PASS"],
        ]).map((r,i)=>passRow(r,[400,1800,1800,1600,2800,1000,1160],i))
      ],[400,1800,1800,1600,2800,1000,1160]),

      pb(),

      // ══════════════════ SECTION 10 ════════════════════════════════════
      h1("10. DEVIATIONS, NON-CONFORMANCES, AND CORRECTIVE ACTIONS"),
      para("During this FAT, two minor Non-Conformance Records (NCRs) were identified and formally documented. Both were classified as minor in nature and did not prevent the overall PASS status of the affected equipment items. Both NCRs were fully rectified during the FAT period prior to close-out of testing on Day 3. The LR Surveyor reviewed and accepted the corrective actions for both NCRs. Formal NCR documents are available in Annex E."),
      tbl([
        hdrRow(["NCR","Date Found","Equipment","Description of Non-Conformance","Corrective Action Taken","Closed","Status"],[900,1200,1500,3000,2500,1000,1060]),
        new TableRow({ children: [
          cell("NCR-001",{w:900,fill:PYELL,bold:true}),
          cell("14 Oct 2025",{w:1200}),
          cell("S-Band Radar Transceiver",{w:1500}),
          mcell(["Minor cosmetic scratch approximately 40 mm in length observed on lower right panel of S-Band radar transceiver during visual inspection. Scratch is superficial and does not affect functionality, performance, or structural integrity. Ref: FAT Procedure §4.1.2"],{w:3000}),
          mcell(["QC Manager confirmed scratch is cosmetic only, no penetration of protective coating. Anti-corrosion treatment applied. Scratch documented photographically and accepted in writing by Owner's Representative (Capt. Zhang Wei) on 15 October 2025. Accepted 'As-Is'."],{w:2500}),
          cell("15 Oct 2025",{w:1000}),
          cell("CLOSED",{w:1060,fill:PGREEN,bold:true,tc:GREEN_T,ctr:true}),
        ]}),
        new TableRow({ children: [
          cell("NCR-002",{w:900,fill:PYELL,bold:true,fill2:MGRAY}),
          cell("15 Oct 2025",{w:1200,fill:MGRAY}),
          cell("ECDIS Primary JAN-9201",{w:1500,fill:MGRAY}),
          mcell(["During Route Monitoring test, anti-grounding look-ahead time was displaying in UTC instead of Local Time (LT) as specified in Purchase Order Technical Specification Appendix B §3.2.11. This is a software configuration issue, not a type-approval non-compliance."],{w:3000,fill:MGRAY}),
          mcell(["JRC Technical Support contacted. Configuration file updated to display look-ahead time in LT (user-configurable). Update applied to both Primary and Backup ECDIS units on 15 October 2025. Re-test performed on Day 3 (16 October 2025): PASS. Witnessed by LR Surveyor and Owner's Representative."],{w:2500,fill:MGRAY}),
          cell("16 Oct 2025",{w:1000,fill:MGRAY}),
          cell("CLOSED",{w:1060,fill:PGREEN,bold:true,tc:GREEN_T,ctr:true}),
        ]}),
      ],[900,1200,1500,3000,2500,1000,1060]),

      pb(),

      // ══════════════════ SECTION 11 ════════════════════════════════════
      h1("11. TEST SUMMARY AND ACCEPTANCE STATEMENT"),
      h2("11.1 Equipment Test Summary"),
      tbl([
        hdrRow(["#","System / Equipment Group","No. of Tests","PASS","FAIL","N/A","Final Status"],[400,3500,1200,1000,1000,1000,2860]),
        ...([
          ["1","X-Band Radar — Visual Inspection","8","8","0","0","PASS"],
          ["2","X-Band Radar — Performance Tests","13","13","0","0","PASS"],
          ["3","X-Band and S-Band Radar — ARPA Tests","9","9","0","0","PASS"],
          ["4","ECDIS (Primary and Backup) — Functional Tests","16","16","0","0","PASS"],
          ["5","Gyrocompass (FOG) — Performance Tests","7","7","0","0","PASS"],
          ["6","GNSS / GPS — Performance Tests","5","5","0","0","PASS"],
          ["7","AIS Class A — Performance Tests","7","7","0","0","PASS"],
          ["8","GMDSS — VHF DSC Tests","6","6","0","0","PASS"],
          ["9","GMDSS — MF/HF, INMARSAT-C and NAVTEX Tests","9","9","0","0","PASS"],
          ["10","VDR — Data Recording Tests","9","9","0","0","PASS"],
          ["11","Bridge Alert Management — Integration Tests","6","6","0","0","PASS"],
          ["12","System Integration — Interface Tests","12","12","0","0","PASS"],
          ["13","SART and AIS-SART — Functional Tests","4","4","0","0","PASS"],
        ]).map((r,i)=>passRow(r,[400,3500,1200,1000,1000,1000,2860],i)),
        new TableRow({ children: [
          cell("",{w:400,fill:NAVY}),
          cell("GRAND TOTAL",{w:3500,fill:NAVY,bold:true,tc:WHITE}),
          cell("113",{w:1200,fill:NAVY,bold:true,tc:WHITE,ctr:true}),
          cell("113",{w:1000,fill:NAVY,bold:true,tc:WHITE,ctr:true}),
          cell("0",{w:1000,fill:NAVY,bold:true,tc:WHITE,ctr:true}),
          cell("0",{w:1000,fill:NAVY,bold:true,tc:WHITE,ctr:true}),
          cell("ALL PASS",{w:2860,fill:NAVY,bold:true,tc:WHITE,ctr:true}),
        ]}),
      ],[400,3500,1200,1000,1000,1000,2860]),

      sp(),
      h2("11.2 Formal Acceptance Statement"),
      para("On the basis of the Factory Acceptance Tests conducted at Neptune Maritime Industries Pte. Ltd., Singapore, from 14 to 16 October 2025, and following the satisfactory close-out of all Non-Conformance Records as detailed in Section 10, the undersigned parties confirm:"),
      bul("All 20 equipment items have been tested and found to comply with applicable type approval standards, IMO performance standards, flag state requirements, and contractual technical specifications."),
      bul("A total of 113 individual test procedures were performed, all resulting in a PASS. Zero test failures remain outstanding."),
      bul("Two NCRs (NCR-001 and NCR-002) were raised during the FAT and formally closed prior to signing of this acceptance statement."),
      bul("The Lloyd's Register Surveyor has witnessed all SOLAS-mandatory tests and confirms the equipment meets LR Classification Rules and IMO requirements for installation aboard MV PACIFIC HORIZON."),
      bul("The RMIS Flag State Inspector confirms no objection to the equipment being installed on a Marshall Islands-flagged vessel."),
      bul("The equipment is hereby APPROVED FOR SHIPMENT to Hyundai Heavy Industries, Ulsan Shipyard, South Korea, for installation and commissioning aboard MV PACIFIC HORIZON."),
      sp(),
      tbl([
        hdrRow(["ROLE","NAME / COMPANY / SIGNATURE","DATE SIGNED"],[3000,5000,1960]),
        new TableRow({ children: [cell("Equipment Supplier (Neptune Maritime Industries)",{w:3000,fill:LGRAY,bold:true}), mcell(["Lim Boon Kiat — QC Manager","Neptune Maritime Industries Pte. Ltd.","_______________________"],{w:5000}), cell("22 October 2025",{w:1960,ctr:true})] }),
        new TableRow({ children: [cell("Shipowner / Operator (Pacific Bulk Carriers)",{w:3000,fill:LGRAY,bold:true}), mcell(["Capt. (Ret.) Zhang Wei — Technical Superintendent","Pacific Bulk Carriers Holding Ltd.","_______________________"],{w:5000}), cell("16 October 2025",{w:1960,ctr:true})] }),
        new TableRow({ children: [cell("Classification Society (Lloyd's Register)",{w:3000,fill:LGRAY,bold:true}), mcell(["Mr. James O'Connor — LR Surveyor","Lloyd's Register — Survey No. LR/SG/2025/0312","_______________________"],{w:5000}), cell("16 October 2025",{w:1960,ctr:true})] }),
        new TableRow({ children: [cell("Flag State Authority (Republic of Marshall Islands)",{w:3000,fill:LGRAY,bold:true}), mcell(["Mr. David Lee — RMIS Authorized Inspector","Republic of Marshall Islands Ship Registry","_______________________"],{w:5000}), cell("16 October 2025",{w:1960,ctr:true})] }),
        new TableRow({ children: [cell("Shipyard (Hyundai Heavy Industries)",{w:3000,fill:LGRAY,bold:true}), mcell(["Ms. Kim Su-Yeon — Equipment Coordinator","Hyundai Heavy Industries Co., Ltd. — Ulsan","_______________________"],{w:5000}), cell("16 October 2025",{w:1960,ctr:true})] }),
      ],[3000,5000,1960]),

      pb(),

      // ══════════════════ SECTION 12 ════════════════════════════════════
      h1("12. ANNEXES AND ATTACHMENTS"),
      tbl([
        hdrRow(["Annex","Title","Document Number","Status"],[900,4000,3200,1860]),
        ...([
          ["Annex A","Pre-FAT Documentation Checklist and Sign-Off Sheet","NMI-FAT-DOC-2025-0847-A","Complete — Signed"],
          ["Annex B","Type Approval Certificate Register — All Equipment","NMI-FAT-DOC-2025-0847-B","Complete — Current TACs Attached"],
          ["Annex C","Calibration Certificates — All Test Instruments","NMI-FAT-DOC-2025-0847-C","Complete — Within Calibration Period"],
          ["Annex D","Equipment Software / Firmware Version Record","NMI-FAT-DOC-2025-0847-D","Complete"],
          ["Annex E","NCR Register — NCR-001 and NCR-002 with Close-Out Records","NMI-FAT-NCR-2025-0847","Complete — Both NCRs Closed"],
          ["Annex F","Photographic Record of FAT — Day 1, 2 and 3","NMI-FAT-PHO-2025-0847","Complete — USB Media Attached"],
          ["Annex G","NMEA Interface Matrix — Verified as-tested","NMI-FAT-ICD-2025-0847","Complete"],
          ["Annex H","VDR Data Playback Verification Report","NMI-FAT-VDR-2025-0847","Complete — LR Surveyor Witnessed"],
          ["Annex I","LR Surveyor's Attendance Certificate","LR/SG/2025/0312-ATT","Original Attached"],
          ["Annex J","Owner's Acceptance Form (Signed Original)","PBC-NMI-FAT-ACC-2025","Original Attached"],
        ]).map((r,i)=>altRow(r,[900,4000,3200,1860],i))
      ],[900,4000,3200,1860]),

      sp(), sp(),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        border: { top: { style: BorderStyle.SINGLE, size: 6, color: NAVY, space: 8 },
                  bottom: { style: BorderStyle.SINGLE, size: 6, color: NAVY, space: 8 } },
        spacing: { before: 200, after: 200 },
        children: [new TextRun({ text: "— END OF FACTORY ACCEPTANCE TEST REPORT —", font: "Arial", size: 26, bold: true, color: NAVY })]
      }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 40 },
        children: [new TextRun({ text: "Document No: NMI-FAT-2025-0847  |  Revision: 02  |  Date: 22 October 2025", font: "Arial", size: 16, color: "666666" })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 0 },
        children: [new TextRun({ text: "Neptune Maritime Industries Pte. Ltd.  |  9 Tuas Basin Link, Singapore 638783  |  +65 6861 0088", font: "Arial", size: 16, color: "666666" })] }),

    ]
  }]
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync('FAT_Report_Final.docx', buf);
  console.log('Done');
}).catch(e => { console.error(e); process.exit(1); });
